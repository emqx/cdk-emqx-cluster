import aws_cdk as cdk
from constructs import Construct
from distutils.util import strtobool

from aws_cdk import (aws_ec2 as ec2, aws_ecs as ecs,
                     Stack,
                     aws_logs as aws_logs,
                     aws_elasticloadbalancingv2 as elb,
                     aws_elasticloadbalancingv2_targets as target,
                     aws_route53 as r53,
                     aws_route53_targets as r53_targets,
                     aws_elasticloadbalancingv2 as elbv2,
                     aws_fis as fis,
                     aws_iam as iam,
                     aws_ssm as ssm,
                     aws_s3 as s3,
                     aws_s3_deployment as s3deploy,
                     aws_efs as efs,
                     aws_msk as msk,
                     aws_eks as eks,
                     aws_ecs_patterns as ecs_patterns)
from aws_cdk import Duration, CfnParameter, RemovalPolicy
from base64 import b64encode
import sys
import logging
import textwrap
import yaml
import json
import random
import string
import os

from cdk_emqx_cluster.cdk_chaos_test import cdk_chaos_test

ubuntu_arm_ami = ec2.MachineImage.from_ssm_parameter('/aws/service/canonical/ubuntu/server/focal/stable/current/arm64/hvm/ebs-gp2/ami-id')
ubuntu_x86_64_ami = ec2.MachineImage.from_ssm_parameter('/aws/service/canonical/ubuntu/server/focal/stable/current/amd64/hvm/ebs-gp2/ami-id')

with open("./user_data/emqx_init.sh") as f:
    emqx_user_data = f.read()

with open("./user_data/loadgen_init.sh") as f:
    loadgen_user_data = f.read()

with open("./user_data/os_common.sh") as f:
    os_common_user_data = f.read()
    user_data_os_common = ec2.UserData.custom(os_common_user_data)

with open("./user_data/nginx.sh") as f:
    user_data_nginx = ec2.UserData.custom(f.read())

with open("./ssm_docs/start_traffic.yaml") as f:
    doc_start_traffic = f.read()


def loadgen_setup_script(n: int, hostname: str) -> str:
    return textwrap.dedent(
        f"""\
        cat <<EOF > /usr/bin/loadgen-setup.sh
        #!/bin/bash
        set -xeu

        hostname {hostname}
        hostnamectl set-hostname {hostname}

        netdev=$(ip route show default | cut -d' ' -f5)
        for x in \$(seq 2 250); do ip addr add 192.168.{n}.\$x dev \$netdev; done


        # emqtt bench escript will not start epmd, so we start it here
        epmd -daemon

        touch /tmp/setup-done
        EOF

        chmod +x /usr/bin/loadgen-setup.sh

        cat <<EOF > /etc/systemd/system/loadgen.service
        [Unit]
        Description=Configures loadgen on every boot

        [Service]
        ExecStart=/bin/bash /usr/bin/loadgen-setup.sh

        [Install]
        WantedBy=multi-user.target
        EOF

        systemctl daemon-reload
        systemctl enable loadgen.service
        systemctl start loadgen.service
        """
    )


def emqx_setup_script(n: int, hostname: str) -> str:
    return textwrap.dedent(
        f"""\
        cat <<EOF > /usr/bin/emqx-setup.sh
        #!/bin/bash
        set -xeu

        hostname {hostname}
        hostnamectl set-hostname {hostname}

        touch /tmp/setup-done
        EOF

        chmod +x /usr/bin/emqx-setup.sh

        cat <<EOF > /etc/systemd/system/emqx-setup.service
        [Unit]
        Description=Configures EMQX on every boot
        Before=emqx.service

        [Service]
        ExecStart=/bin/bash /usr/bin/emqx-setup.sh

        [Install]
        WantedBy=multi-user.target
        EOF

        systemctl daemon-reload
        systemctl enable emqx-setup.service
        systemctl start emqx-setup.service
        """
    )


class CdkEmqxClusterStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.exp1 = None
        self.kafka = None

        # The code that defines your stack goes here
        if self.node.try_get_context("tags"):
            self.user_defined_tags = self.node.try_get_context(
                "tags").split(' ')
        else:
            self.user_defined_tags = None

        self.loadbalancer_dnsname = ""
        self.s3_bucket_policy = None

        self.hosts = []
        self.loadgens = []

        # Prepare infrastructure
        self.set_cluster_name()

        # Read context params
        self.read_param()

        self.setup_ssh_key()
        self.setup_s3()
        self.setup_vpc()
        self.setup_sg()
        self.setup_r53()
        self.setup_lb()
        self.setup_efs()

        # Create Application Services
        self.setup_kafka()
        self.setup_pulsar()
        self.setup_emqx(self.numEmqx)
        self.setup_etcd()
        self.setup_loadgen(self.numLg)
        self.setup_monitoring(self.hosts)

        # Setup Bastion
        self.setup_bastion()

        # Outputs
        self.cfn_outputs()

    # %% followings are internals

    def cfn_outputs(self):
        cdk.CfnOutput(self, "ClusterName",
                       value=self.cluster_name)
        cdk.CfnOutput(self, "Loadbalancer",
                       value=self.nlb.load_balancer_dns_name)
        cdk.CfnOutput(self, "SSH Entrypoint",
                       value=self.bastion.instance_public_ip)
        cdk.CfnOutput(self, "Hosts are", value='\n'.join(self.hosts))
        cdk.CfnOutput(self, "SSH Commands for Access",
                       value=f"ssh -A -l ec2-user {self.bastion.instance_public_ip} "
                             f"-L 8888:{self.mon_lb}:80 "
                             f"-L 13000:{self.mon_lb}:3000 "
                             f"-L 19090:{self.mon_lb}:9090 "
                             f"-L 15432:{self.mon_lb}:5432 "
                             f"-L 28083:{self.mon_lb}:8083 "
                             "2>/dev/null"
                       )
        cdk.CfnOutput(self, 'EFS ID:', value=self.shared_efs.file_system_id)
        cdk.CfnOutput(self, 'Monitoring Postgres Password:', value=self.postgresPass)

        if self.kafka_ebs_vol_size:
            cdk.CfnOutput(self, 'KAFKA Brokers:', value=self.kafka.bootstrap_brokers)
            cdk.CfnOutput(self, 'KAFKA TLS Brokers:', value=self.kafka.bootstrap_brokers_tls)
            cdk.CfnOutput(self, 'KAFKA ZK:', value=self.kafka.zookeeper_connection_string)

    def setup_loadgen(self, N):
        vpc = self.vpc
        zone = self.int_zone
        sg = self.sg
        key = self.ssh_key
        target = self.nlb.load_balancer_dns_name

        # we let CDK create the first role for this service in the
        # first instance and them use it in subsequent instances
        vm_role = None

        for n in range(0, N):
            name = "loadgen-%d" % n
            loadgen_user_data_template = string.Template(loadgen_user_data)
            bootScript = ec2.UserData.custom(
                loadgen_user_data_template.safe_substitute(
                    EMQTT_BENCH_SRC_CMD = self.emqtt_bench_src_cmd,
                    EMQTTB_SRC_CMD = self.emqttb_src_cmd,
                )
            )

            persistentConfig = ec2.UserData.for_linux()
            persistentConfig.add_commands(
                loadgen_setup_script(n, name + self.domain))

            runscript = ec2.UserData.for_linux()
            runscript.add_commands(textwrap.dedent(
                """\
                cat << EOF > /root/emqtt-bench/run.sh
                #!/bin/bash
                ulimit -n 80000000
                cd /root/emqtt-bench
                ipaddrs=\$(ip addr |grep -o '192.*/32' | sed 's#/32##g' | paste -s -d , -)
                _build/default/bin/emqtt_bench sub -h %s -t "root/%%c/1/+/abc/#" -c 4000000 --prefix "prefix%d" --ifaddr \$ipaddrs -i 5
                EOF
                chmod +x /root/emqtt-bench/run.sh
                """ % (target, n)
            ))
            runscript.add_commands(textwrap.dedent(
                """\
                cat << EOF > /root/emqtt-bench/with-ipaddrs.sh
                #!/bin/bash
                ulimit -n 8000000
                ipaddrs=\$(ip addr | grep -o '192.*/32' | sed 's#/32##g' | paste -s -d , -)
                "\$@" --ifaddr \$ipaddrs
                EOF
                chmod +x /root/emqtt-bench/with-ipaddrs.sh
                """
            ))
            # make the hostname persistent across reboots
            runscript.add_commands("""\
            if ! grep -q 'preserve_hostname: true' /etc/cloud/cloud.cfg
            then
              if ! grep -q 'preserve_hostname:' /etc/cloud/cloud.cfg
              then
                echo 'preserve_hostname: true' >> /etc/cloud/cloud.cfg
              else
                sed -i -e 's/preserve_hostname: false/preserve_hostname: true/' /etc/cloud/cloud.cfg
              fi
            fi
            """)

            multipartUserData = ec2.MultipartUserData()
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(user_data_os_common))
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(bootScript))
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(persistentConfig))
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(runscript))

            if (self.loadgen_ins_type[2] == 'g'): #Graviton2
                ami = ubuntu_arm_ami
            else:
                ami = ubuntu_x86_64_ami

            lg_vm = ec2.Instance(self, id=name,
                                 instance_type=ec2.InstanceType(
                                     instance_type_identifier=self.loadgen_ins_type),
                                 machine_image=ami,
                                 user_data=multipartUserData,
                                 security_group=sg,
                                 key_name=key,
                                 role=vm_role,
                                 vpc=vpc,
                                 source_dest_check=False
                                 )
            vm_role = lg_vm.role
            self.attach_ssm_policy(vm_role)
            # add routes for traffic from loadgen
            i = 1
            for net in vpc.private_subnets:
                net.add_route(id=name+str(i),
                              router_id=lg_vm.instance_id,
                              router_type=ec2.RouterType.INSTANCE,
                              destination_cidr_block="192.168.%d.0/24" % n)
                i += 1

            dnsname = "%s%s" % (name, self.domain)
            r53.ARecord(self,
                        id=dnsname,
                        record_name=dnsname,
                        zone=zone,
                        target=r53.RecordTarget([lg_vm.instance_private_ip])
                        )

            self.hosts.append(dnsname)
            self.loadgens.append(dnsname)

            if self.user_defined_tags:
                cdk.Tags.of(ins).add(*self.user_defined_tags)
            self.attach_s3_policy(vm_role)
            cdk.Tags.of(lg_vm).add('service', 'loadgen')
            cdk.Tags.of(lg_vm).add('cluster', self.cluster_name)

    def setup_monitoring(self, targets):
        vpc = self.vpc
        sg = self.sg
        nlb = self.nlb
        with open("./user_data/prometheus.yml") as f:
            prometheus_config_tmpl = string.Template(f.read())
            prometheus_config = prometheus_config_tmpl.safe_substitute(
                EMQX_NODES = ','.join([f'"{t}:9100"' for t in targets]),
                EMQTTB_NODES = ','.join([f'"{t}:8017"' for t in self.loadgens]),
            )

        sg.add_ingress_rule(ec2.Peer.any_ipv4(),
                            ec2.Port.tcp(9090), 'prometheus')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(
            9100), 'prometheus node exporter')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(
            9091), 'prometheus pushgateway')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(3000), 'grafana')
        if self.enable_postgres:
            sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432), 'postgres')

        self.ap_prom_data = efs.AccessPoint(self, "shared-data-prom",
                                            path='/tsdb_data',
                                            create_acl=efs.Acl(
                                                owner_uid="65534",
                                                owner_gid="65534",
                                                permissions="777"
                                            ),
                                            posix_user=efs.PosixUser(
                                                uid="65534",  # nobody
                                                gid="65534"),
                                            file_system=self.shared_efs)
        if self.enable_postgres:
            self.ap_pgsql_data = efs.AccessPoint(self, "shared-data-pgsql",
                                                 path='/pgsql_data',
                                                 create_acl=efs.Acl(
                                                     owner_uid="0",
                                                     owner_gid="0",
                                                     permissions="777"
                                                 ),
                                                 posix_user=efs.PosixUser(
                                                     uid="0",  # nobody
                                                     gid="0"),
                                                 file_system=self.shared_efs)

        self.prom_data_vol = ecs.Volume(
            name="prom_data",
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=self.shared_efs.file_system_id,
                transit_encryption='ENABLED',
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=self.ap_prom_data.access_point_id),
            )
        )
        if self.enable_postgres:
            self.pgsql_data_vol = ecs.Volume(
                name="pgsql_data",
                efs_volume_configuration=ecs.EfsVolumeConfiguration(
                    file_system_id=self.shared_efs.file_system_id,
                    transit_encryption='ENABLED',
                    authorization_config=ecs.AuthorizationConfig(
                        access_point_id=self.ap_pgsql_data.access_point_id),
                )
            )

        cluster = ecs.Cluster(self, "Monitoring", vpc=vpc)

        volumes = [
            self.prom_data_vol,
        ]
        if self.enable_postgres:
            volumes.append(self.pgsql_data_vol)
        task = ecs.FargateTaskDefinition(self,
                                         id='MonitorTask',
                                         cpu=512,
                                         memory_limit_mib=4096,
                                         volumes=volumes
                                        )
        task.add_volume(name='prom_config')
        c_config = task.add_container('config-prometheus',
                                      image=ecs.ContainerImage.from_registry(
                                          'bash'),
                                      essential=False,
                                      # uncomment for troubleshooting
                                      # logging=ecs.LogDriver.aws_logs(stream_prefix="mon_config_prometheus",
                                      #                               log_retention=aws_logs.RetentionDays.ONE_DAY
                                      #                               ),
                                      command=["-c",
                                               "echo $DATA | base64 -d - | tee /tmp/private/prometheus.yml"
                                               ],
                                      environment={
                                          'DATA': cdk.Fn.base64(prometheus_config)}

                                      )
        c_config.add_mount_points(ecs.MountPoint(
            read_only=False, container_path='/tmp/private', source_volume='prom_config'))
        c_prometheus = task.add_container('prometheus',
                                          essential=False,
                                          # https://github.com/prometheus/prometheus/blob/main/Dockerfile
                                          image=ecs.ContainerImage.from_registry(
                                              'prom/prometheus'),
                                          port_mappings=[ecs.PortMapping(
                                              container_port=9090)],
                                          command=[
                                              "--config.file=/etc/prometheus/private/prometheus.yml",
                                              "--storage.tsdb.path=/prometheus/tsdb_data",
                                              "--web.console.libraries=/usr/share/prometheus/console_libraries",
                                              "--web.console.templates=/usr/share/prometheus/consoles",
                                              "--storage.tsdb.retention.time=1y",
                                              "--web.enable-admin-api"
                                          ],
                                          # uncomment for troubleshooting
                                          # logging=ecs.LogDriver.aws_logs(stream_prefix="mon_prometheus",
                                          #                               log_retention=aws_logs.RetentionDays.ONE_DAY
                                          #                               ),

                                          )
        c_prometheus.add_mount_points(ecs.MountPoint(
            read_only=False, container_path='/etc/prometheus/private', source_volume='prom_config'))
        c_prometheus.add_mount_points(ecs.MountPoint(
            read_only=False, container_path='/prometheus/tsdb_data', source_volume=self.prom_data_vol.name))
        c_prometheus.add_container_dependencies(ecs.ContainerDependency(
            container=c_config, condition=ecs.ContainerDependencyCondition.COMPLETE))

        c_pushgateway = task.add_container('pushgateway',
                                           essential=False,
                                           image=ecs.ContainerImage.from_registry(
                                               'prom/pushgateway'),
                                           port_mappings=[
                                               ecs.PortMapping(container_port=9091)]
                                           )
        if self.enable_postgres:
            c_postgres = task.add_container('postgres',
                                            essential=True,
                                            image=ecs.ContainerImage.from_registry(
                                                'ghcr.io/iequ1/sysmon-postgres:1.5.0'),
                                            port_mappings=[
                                                ecs.PortMapping(container_port=5432)],
                                            # It looks like postgres doesn't want to die sometimes
                                            stop_timeout=Duration.seconds(100),
                                            start_timeout=Duration.seconds(300),
                                            environment={
                                                'POSTGRES_PASSWORD': self.postgresPass,
                                                'SYSMON_PASS': self.postgresPass,
                                                'GRAFANA_PASS': self.postgresPass,
                                                # must not use "/var/lib/postgresql/data", else it'll
                                                # fail
                                                'PGDATA': '/var/lib/postgresql/pgdata'
                                            },
                                            # uncomment to reset the WAL; it may resolve a
                                            # stuck container after a
                                            # redeploy.
                                            # user="postgres",
                                            # command=[
                                            #     "pg_resetwal",
                                            #     "-f",
                                            #     "/var/lib/postgresql/pgdata",
                                            # ],
                                            # uncomment for troubleshooting
                                            # logging=ecs.LogDriver.aws_logs(stream_prefix="mon_postgres",
                                            #                                log_retention=aws_logs.RetentionDays.ONE_DAY,
                                            #                                ),
                                            )
            c_postgres.add_mount_points(
                ecs.MountPoint(
                    read_only=False,
                    # must be the same as the PGDATA variable above
                    container_path='/var/lib/postgresql/pgdata',
                    source_volume=self.pgsql_data_vol.name,
                ),
            )

        c_grafana = task.add_container('grafana',
                                       essential=True,
                                       image=ecs.ContainerImage.from_registry(
                                           'ghcr.io/iequ1/sysmon-grafana:1.5.0'),
                                       environment={
                                           'POSTGRES_PASS': self.postgresPass,
                                           'GF_AUTH_ANONYMOUS_ENABLED': "true"
                                       },
                                       port_mappings=[
                                           ecs.PortMapping(container_port=3000)]
                                       )

        service = ecs.FargateService(self, "EMQXMonitoring",
                                     security_groups=[self.sg],
                                     cluster=cluster,
                                     task_definition=task,
                                     desired_count=1,
                                     assign_public_ip=False
                                     )

        service.connections.allow_from(
            self.sg_efs_mt, ec2.Port.all_traffic(), "Allow EFS access")

        listenerGrafana = nlb.add_listener('grafana', port=3000)
        listenerPrometheus = nlb.add_listener('prometheus', port=9090)
        listenerPushGateway = nlb.add_listener('pushgateway', port=9091)

        listenerGrafana.add_targets(id='grafana', port=3000, targets=[service.load_balancer_target(
            container_name="grafana",
            container_port=3000
        )])
        listenerPrometheus.add_targets(id='prometheus', port=9090, targets=[service.load_balancer_target(
            container_name="prometheus",
            container_port=9090
        )])

        listenerPushGateway.add_targets(id='pushgateway', port=9091, targets=[service.load_balancer_target(
            container_name="pushgateway",
            container_port=9091
        )]),

        if self.enable_postgres:
            listenerPostgres = nlb.add_listener('postgres', port=5432)
            listenerPostgres.add_targets(id='postgres', port=5432, targets=[service.load_balancer_target(
                container_name="postgres",
                container_port=5432
            )]),

        self.mon_lb = self.loadbalancer_dnsname
        cdk.CfnOutput(self, "Monitoring Grafana",
                       value="%s:%d" % (self.mon_lb, 3000))
        cdk.CfnOutput(self, "Monitoring Prometheus",
                       value="%s:%d" % (self.mon_lb, 9090))


    def setup_emqx(self, N):
        vpc = self.vpc
        zone = self.int_zone
        sg = self.sg
        key = self.ssh_key
        nlb = self.nlb
        self.emqx_vms = []
        self.emqx_core_nodes = []

        # we let CDK create the first role for this service in the
        # first instance and them use it in subsequent instances
        vm_role = None

        for n in range(0, N):
            name = "emqx-%d" % n
            dnsname = name + self.domain
            isCore = n <= self.numCoreNodes - 1
            dbBackendRole = "core" if isCore else "replicant"
            if isCore:
                self.emqx_core_nodes.append("emqx@" + dnsname)
            if self.emqx_ebs_vol_size and int(self.emqx_ebs_vol_size) > 0:
                blockdevs = [ec2.BlockDevice(
                    device_name='/dev/xvda', volume=ec2.BlockDeviceVolume.ebs(int(self.emqx_ebs_vol_size)))]
            else:
                blockdevs = []

            persistentConfig = ec2.UserData.for_linux()
            persistentConfig.add_commands(emqx_setup_script(n, dnsname))

            hostname_cloud_init = ec2.UserData.for_linux()
            # make the hostname persistent across reboots
            hostname_cloud_init.add_commands("""\
            if ! grep -q 'preserve_hostname: true' /etc/cloud/cloud.cfg
            then
              if ! grep -q 'preserve_hostname:' /etc/cloud/cloud.cfg
              then
                echo 'preserve_hostname: true' >> /etc/cloud/cloud.cfg
              else
                sed -i -e 's/preserve_hostname: false/preserve_hostname: true/' /etc/cloud/cloud.cfg
              fi
            fi
            """)

            userdata_init = ec2.UserData.for_linux()
            userdata_init.add_commands('cd /root')
            userdata_init.add_commands(self.emqx_src_cmd)
            userdata_init.add_commands(f"EMQX_CDK_POSTGRES_PASS={self.postgresPass}")
            userdata_init.add_commands(f"EMQX_CDK_DB_BACKEND={self.dbBackend}")
            userdata_init.add_commands(
                f"EMQX_CDK_DB_BACKEND_ROLE={dbBackendRole}")
            if not isCore:
                userdata_init.add_commands(
                    f"EMQX_CDK_CORE_NODES={','.join(self.emqx_core_nodes)}")
            userdata_init.add_commands(f"EMQX_BUILDER_IMAGE={self.emqx_builder_image}")
            userdata_init.add_commands(f"EMQX_BUILD_PROFILE={self.emqx_build_profile}")
            userdata_init.add_commands(emqx_user_data)

            multipartUserData = ec2.MultipartUserData()
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(persistentConfig))
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(hostname_cloud_init))
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(user_data_os_common))
            multipartUserData.add_part(
                ec2.MultipartBody.from_user_data(userdata_init))
            if self.enable_nginx:
                multipartUserData.add_part(
                    ec2.MultipartBody.from_user_data(user_data_nginx))

            if isCore:
                ins_type = self.emqx_core_ins_type
            else:
                ins_type = self.emqx_ins_type

            if (ins_type[2] == 'g'): #Graviton2
                ami = ubuntu_arm_ami
            else:
                ami = ubuntu_x86_64_ami

            vm = ec2.Instance(self, id=name,
                              instance_type=ec2.InstanceType(
                                  instance_type_identifier=ins_type),
                              block_devices=blockdevs,
                              machine_image=ami,
                              user_data=multipartUserData,
                              security_group=sg,
                              key_name=key,
                              role=vm_role,
                              vpc=vpc,
                              vpc_subnets=ec2.SubnetSelection(
                                  subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
                              )
            vm_role = vm.role
            self.attach_ssm_policy(vm_role)
            self.attach_s3_policy(vm_role)
            self.emqx_vms.append(vm)

            r53.ARecord(self, id=dnsname,
                        record_name=dnsname,
                        zone=zone,
                        target=r53.RecordTarget([vm.instance_private_ip])
                        )
            self.hosts.append(dnsname)

            # tagging
            if self.user_defined_tags:
                cdk.Tags.of(vm).add(*self.user_defined_tags)
            cdk.Tags.of(vm).add('service', 'emqx')

            # tag ins for chaos testing with AWS FIS
            cdk.Tags.of(vm).add('chaos_ready', 'true')
            cdk.Tags.of(vm).add('cluster', self.cluster_name)

        # Add LB endpoints
        listener = nlb.add_listener("port1883", port=1883)
        listenerTLS = nlb.add_listener(
            "port8883", port=8883)  # TLS, emqx terminataion
        listenerQuic = nlb.add_listener(
            "port14567", port=14567, protocol=elbv2.Protocol.UDP)
        listenerWS = nlb.add_listener(
            "port8083", port=8083)
        listenerUI = nlb.add_listener("port80", port=80)

        listener.add_targets('ec2',
                             port=1883,
                             targets=[target.InstanceTarget(x)
                                      for x in self.emqx_vms])
        # @todo we need ssl terminataion
        listenerUI.add_targets('ec2',
                               port=18083,
                               targets=[target.InstanceTarget(x)
                                        for x in self.emqx_vms])

        listenerQuic.add_targets('ec2',
                                 port=14567,
                                 protocol=elbv2.Protocol.UDP,
                                 targets=[target.InstanceTarget(x)
                                          for x in self.emqx_vms])

        listenerWS.add_targets('ec2',
                               port=8083,
                               targets=[target.InstanceTarget(x)
                                        for x in self.emqx_vms])

        listenerTLS.add_targets('ec2',
                                port=8883,
                                targets=[target.InstanceTarget(x)
                                         for x in self.emqx_vms])
        if self.enable_nginx:
            listenerTLSNginx = nlb.add_listener("port18883", port=18883)
            listenerTLSNginx.add_targets('ec2',
                                         port=18883,
                                         targets=[target.InstanceTarget(x)
                                                  for x in self.emqx_vms])

    def setup_etcd(self):
        # if there's no EMQ X nodes (for example, starting up cluster
        # just to analyze past data from Prometheus/Postgres), we
        # don't neet to spin up etcd
        if self.numEmqx == 0:
            return

        # we let CDK create the first role for this service in the
        # first instance and them use it in subsequent instances
        vm_role = None

        for n in range(0, 3):
            vpc = self.vpc
            zone = self.int_zone
            sg = self.sg
            key = self.ssh_key
            # cdk bug?
            (cloud_user_data, ) = ec2.UserData.for_linux(),
            # @TODO: fix domain name as following
            cloud_user_data.add_commands('apt update',
                                         'apt install -y etcd-server etcd-client',
                                         'export EMQX_CLUSTER_DOMAIN="%s"' % self.domain,
                                         "echo ETCD_INITIAL_ADVERTISE_PEER_URLS=http://etcd%d${EMQX_CLUSTER_DOMAIN}:2380 >> /etc/default/etcd" % n,
                                         'echo ETCD_LISTEN_PEER_URLS=http://0.0.0.0:2380 >> /etc/default/etcd',
                                         'echo ETCD_LISTEN_CLIENT_URLS=http://0.0.0.0:2379 >> /etc/default/etcd',
                                         "echo ETCD_ADVERTISE_CLIENT_URLS=http://etcd%d${EMQX_CLUSTER_DOMAIN}:2379 >> /etc/default/etcd" % n,
                                         "echo ETCD_NAME=infra%d >> /etc/default/etcd" % n,
                                         'echo ETCD_INITIAL_CLUSTER_STATE=new >> /etc/default/etcd',
                                         'echo ETCD_INITIAL_CLUSTER_TOKEN=emqx-cluster-1 >> /etc/default/etcd',
                                         'echo ETCD_INITIAL_CLUSTER="infra0=http://etcd0${EMQX_CLUSTER_DOMAIN}:2380,infra1=http://etcd1${EMQX_CLUSTER_DOMAIN}:2380,infra2=http://etcd2${EMQX_CLUSTER_DOMAIN}:2380" >> /etc/default/etcd',
                                         'echo ETCD_UNSUPPORTED_ARCH=arm64 >> /etc/default/etcd',
                                         'systemctl restart etcd'
                                         )
            ins = ec2.Instance(self, id="etcd.%d" % n,
                               instance_type=ec2.InstanceType(
                                   instance_type_identifier="t4g.nano"),
                               machine_image=ubuntu_arm_ami,
                               user_data=cloud_user_data,
                               security_group=sg,
                               key_name=key,
                               role=vm_role,
                               vpc=vpc
                               )
            vm_role = ins.role
            dnsname = "etcd%d" % n + self.domain
            r53.ARecord(self, id=dnsname,
                        record_name=dnsname,
                        zone=zone,
                        target=r53.RecordTarget([ins.instance_private_ip])
                        )
            self.hosts.append(dnsname)

            if self.user_defined_tags:
                cdk.Tags.of(ins).add(*self.user_defined_tags)
            cdk.Tags.of(ins).add('service', 'etcd')

    def setup_vpc(self):
        max_azs = 2 if self.kafka_ebs_vol_size or self.enable_pulsar else 1
        vpc = ec2.Vpc(self, "VPC EMQX %s" % self.cluster_name,
                      max_azs=max_azs,
                      cidr="10.10.0.0/16",
                      # configuration will create 3 groups in 2 AZs = 6 subnets.
                      subnet_configuration=[
                          ec2.SubnetConfiguration(
                              subnet_type=ec2.SubnetType.PUBLIC,
                              name="Public",
                              cidr_mask=24
                          ),
                          ec2.SubnetConfiguration(
                              subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                              name="Private",
                              cidr_mask=24
                          )],
                      nat_gateways=1
                      )
        self.vpc = vpc

    def set_cluster_name(self):
        self.cluster_name = cdk.Stack.of(self).stack_name
        if not self.cluster_name:
            sys.exit("Cannot define cluster_name")
        self.domain = ".int.%s" % self.cluster_name
        logging.warning(f"✅  Cluster name: {self.cluster_name}")

    def setup_r53(self):
        self.r53_zone_name = "%s_emqx_hosted_zone" % self.cluster_name
        self.int_zone = r53.PrivateHostedZone(self, self.r53_zone_name,
                                              zone_name="int.%s" % self.cluster_name,
                                              vpc=self.vpc
                                              )

    def setup_ssh_key(self):
        self.ssh_key = CfnParameter(self, "sshkey",
                                    type="String", default="key_ireland",
                                    description="Specify your SSH key").value_as_string

    def setup_sg(self):
        """
        Setup security group, one for EC2 instances, because I am lazy.
        """
        sg = ec2.SecurityGroup(self, id='sg_int', vpc=self.vpc)
        # allow any ingress traffic
        sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.all_traffic())
        self.sg = sg

    def setup_s3(self):
        self.s3_bucket_name = 'emqx-cdk-cluster'
        Bucket = s3.Bucket.from_bucket_name(self, self.s3_bucket_name, self.s3_bucket_name)
        if not Bucket:
            Bucket = s3.Bucket(self, id=self.s3_bucket_name, auto_delete_objects=False,
                               bucket_name=self.s3_bucket_name,
                               )

        s3deploy.BucketDeployment(self, "DeployHelperScripts",
                                  sources=[s3deploy.Source.asset(os.path.join('./user_data', 'bin'))],
                                  destination_bucket=Bucket,
                                  destination_key_prefix=f"{self.cluster_name}/bin/"
                                  )

    def setup_bastion(self):
        """
        This is a SSH proxy/middleman sit between Internet and VPC.
        """
        sg_bastion = ec2.SecurityGroup(self, id='sg_bastion', vpc=self.vpc)
        sg_bastion.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(22), 'SSH from anywhere')
        bastion = ec2.BastionHostLinux(self, "Bastion",
                                       vpc=self.vpc,
                                       subnet_selection=ec2.SubnetSelection(
                                           subnet_type=ec2.SubnetType.PUBLIC),
                                       security_group=sg_bastion,
                                       instance_name="BastionHostLinux %s" % self.cluster_name,
                                       instance_type=ec2.InstanceType(instance_type_identifier="t3.nano"))
        # allow uploading TSDB snapshots to S3
        self.attach_s3_policy(bastion.role)

        bastion.instance.instance.add_property_override(
            "KeyName", self.ssh_key)
        bastion.connections.allow_from_any_ipv4(
            ec2.Port.tcp(22), "Internet access SSH")

        bastion.instance.add_user_data(textwrap.dedent(
            """
            #!/bin/bash
            curl -o kubectl https://s3.us-west-2.amazonaws.com/amazon-eks/1.21.2/2021-07-05/bin/linux/amd64/kubectl
            install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
            curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 > get_helm.sh
            chmod 700 get_helm.sh
            ./get_helm.sh --version v3.8.2
            yum install -y tmux amazon-efs-utils
            echo "search int.%s" >> /etc/resolv.conf
            sudo -u ec2-user echo 'HOST *' > ~ec2-user/.ssh/config
            sudo -u ec2-user echo "USER ubuntu" >> ~ec2-user/.ssh/config
            mkdir -p /mnt/efs-data
            mount -t efs -o tls %s:/ /mnt/efs-data
            """ % (self.cluster_name, self.shared_efs.file_system_id)
        ))
        if self.kafka_ebs_vol_size:
            bastion.instance.add_user_data(
            f"""
            #!/bin/bash
            sudo yum install -y java-1.8.0
            wget https://archive.apache.org/dist/kafka/2.2.1/kafka_2.12-2.2.1.tgz
            tar zxvf kafka_2.12-2.2.1.tgz
            cd kafka_2.12-2.2.1
            bin/kafka-topics.sh --create --zookeeper "{self.kafka.zookeeper_connection_string}" --replication-factor 2 --partitions 12 --topic t1 --config segment.bytes=200000000 --config retention.ms=3600000
            """)

            with open("./user_data/emqx-kafka-rule-engine.json") as f:
                template = f.read()
                config_dump = json.loads(template)
                # jq path:  .resources[].config.servers
                config_dump['resources'][0]['config']['servers'] = self.kafka.bootstrap_brokers
                config_json = json.dumps(config_dump)

            bastion.instance.add_user_data(
            textwrap.dedent(f"""
            #!/bin/bash
            cat > emqx_config.json << EOF
            {config_json}
            EOF
            curl -i --basic -u admin:public -X POST "http://emqx-0.int.{self.cluster_name}:8081/api/v4/data/import" \
            -d @emqx_config.json
            """))

        if self.enable_pulsar:
            pulsar_resource = self.pulsar_eks_cluster.cluster_arn
            pulsar_control_plane_role = self.pulsar_eks_cluster.role.role_arn
            pulsar_admin_role = self.pulsar_eks_cluster.admin_role.role_arn
            pulsar_kubectl_role = self.pulsar_eks_cluster.kubectl_role.role_arn
            # https://github.com/aws/aws-cdk/issues/13167#issuecomment-782884496
            pulsar_master_role = self.pulsar_eks_cluster.node.try_find_child("MastersRole").role_arn
            pulsar_policy = iam.Policy(
                self,
                id=self.cluster_name + "-pulsar-eks-cluster-bastion",
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "eks:DescribeCluster",
                            "sts:AssumeRole",
                        ],
                        effect=iam.Effect.ALLOW,
                        resources=[
                            pulsar_resource,
                            pulsar_admin_role,
                            pulsar_kubectl_role,
                            pulsar_control_plane_role,
                            pulsar_master_role,
                        ]
                    )
                ],
            )
            bastion.role.attach_inline_policy(pulsar_policy)
            self.pulsar_eks_cluster.kubectl_security_group.add_ingress_rule(
                peer=sg_bastion, connection=ec2.Port.all_traffic()
            )

        self.sg_efs_mt.add_ingress_rule(
            peer=sg_bastion, connection=ec2.Port.all_traffic())
        self.bastion = bastion

    def setup_lb(self):
        """
        Setup network load balancer
        """
        self.loadbalancer_dnsname = 'lb' + self.domain
        nlb = elb.NetworkLoadBalancer(self, "emqx-elb",
                                      vpc=self.vpc,
                                      internet_facing=False,
                                      cross_zone_enabled=True,
                                      vpc_subnets=ec2.SubnetSelection(
                                          one_per_az=True),
                                      load_balancer_name="emqx-nlb-%s" % self.cluster_name)
        r53.ARecord(self, "AliasRecord",
                    zone=self.int_zone,
                    record_name=self.loadbalancer_dnsname,
                    target=r53.RecordTarget.from_alias(
                        r53_targets.LoadBalancerTarget(nlb))
                    )
        self.nlb = nlb

    # Uncomment to force given AZ(s) to be used.
    # @property
    # def availability_zones(self):
    #     return ["sa-east-1b"]

    def read_param(self):
        # CHAOS_READY, if true, cluster is chaos ready and able to accept chaos tests.
        self.is_chaos_ready = self.node.try_get_context('chaos') or 'False'
        self.is_chaos_ready = strtobool(self.is_chaos_ready)

        # EMQX Instance Type
        # https://aws.amazon.com/ec2/instance-types/
        # suggested m5.2xlarge
        self.emqx_ins_type = self.node.try_get_context(
            'emqx_ins_type') or 't3a.small'

        # Instance size for core nodes (when using RLOG DB backend)
        # defaults to `emqx_ins_type' if unspecified
        self.emqx_core_ins_type = self.node.try_get_context(
            'emqx_core_ins_type') or self.emqx_ins_type

        # Number of EMQXs
        self.numEmqx = int(self.node.try_get_context('emqx_n') or 2)

        # Type of DB Backend
        # choice: "mnesia" | "rlog"
        # default: "mnesia"
        dbBackend = self.node.try_get_context('emqx_db_backend') or "mnesia"
        dbBackendChoices = ("mnesia", "rlog")
        if dbBackend not in dbBackendChoices:
            logging.error(
                f"👎 parameter `emqx_db_backend' must be one of: {dbBackendChoices}")
            raise RuntimeError(f"invalid `emqx_db_backend': {dbBackend}")
        self.dbBackend = dbBackend
        self.postgresPass = self.node.try_get_context(
            'emqx_monitoring_postgres_password') or self.cluster_name

        # Number of core nodes. Only relevant if `emqx_db_backend' = "rlog"
        # default: same as `emqx_n'
        numCoreNodes = int(self.node.try_get_context(
            'emqx_num_core_nodes') or self.numEmqx)
        if numCoreNodes > self.numEmqx:
            logging.error(
                f"👎 parameter `emqx_num_core_nodes' must be less or equal to `emqx_n'")
            raise RuntimeError(
                f"invalid `emqx_num_core_nodes': {numCoreNodes}")
        self.numCoreNodes = numCoreNodes

        # LOADGEN Instance Type
        # suggested m5n.xlarge
        self.loadgen_ins_type = self.node.try_get_context(
            'loadgen_ins_type') or 't3a.small'

        # Number of LOADGENS
        self.numLg = int(self.node.try_get_context('lg_n') or 1)

        # Extra EBS vol size for EMQX DATA per EMQX Instance
        self.emqx_ebs_vol_size = self.node.try_get_context('emqx_ebs')

        # Kafka
        self.kafka_ebs_vol_size = self.node.try_get_context(
            'kafka_ebs') or None

        # Enable Nginx
        # Nginx is used for SSL termination for EMQ X.  But it spawns
        # one worker process per machine core, so for large machines
        # like `c6g.metal` it may take 19.2 % of the memory at rest.
        enable_nginx = self.node.try_get_context('emqx_enable_nginx')
        if enable_nginx:
            self.enable_nginx = enable_nginx.lower() != "false"
        else:
            self.enable_nginx = True

        # Preserve EFS
        # set it to 'False' to create new tmp EFS that will be destoryed after cluster get destroyed.
        # set it to 'True' to create new and the EFS will be preserved after cluster get destroyed.
        # set it to FIS id (like 'fs-0c86dd7fcd8ca836c') to reuse the preserved EFS without create new one.
        self.retain_efs = self.node.try_get_context('retain_efs')
        if isinstance(self.retain_efs, str) and not self.retain_efs.startswith('fs-'):
            self.retain_efs = strtobool(self.retain_efs)

        # EMQX source
        self.emqx_src_cmd = self.node.try_get_context(
            'emqx_src') or "git clone https://github.com/emqx/emqx"

        # EMQTTB source
        self.emqttb_src_cmd = self.node.try_get_context(
            'emqttb_src_cmd') or 'git clone -b "master" https://github.com/emqx/emqttb.git'

        # EMQTT-Bench source
        self.emqtt_bench_src_cmd = self.node.try_get_context(
            'emqtt_bench_src_cmd') or 'git clone -b "master" https://github.com/emqx/emqtt-bench.git'

        # EMQX-Builder image that'll build the release
        self.emqx_builder_image = self.node.try_get_context(
            'emqx_builder_image') or "ghcr.io/emqx/emqx-builder/5.0-17:1.13.4-24.2.1-1-ubuntu20.04"

        # EMQ X profile to be built with "make $PROFILE"
        self.emqx_build_profile = self.node.try_get_context(
            'emqx_build_profile') or "emqx-pkg"

        # deploy pulsar?
        enable_pulsar = self.node.try_get_context('emqx_pulsar_enable')
        if enable_pulsar and isinstance(enable_pulsar, str):
            self.enable_pulsar = strtobool(enable_pulsar)
        else:
            self.enable_pulsar = False

        # deploy postgres?
        enable_postgres = self.node.try_get_context('emqx_postgres_enable')
        if enable_postgres and isinstance(enable_postgres, str):
            self.enable_postgres = strtobool(enable_postgres)
        else:
            self.enable_postgres = True

        if self.emqx_ins_type != self.emqx_core_ins_type:
            logging.warning("👍🏼  Will deploy %d %s EMQX, %d %s EMQX, and %d %s Loadgens\n get emqx src by %s "
                            % (self.numEmqx - self.numCoreNodes,
                               self.emqx_ins_type,
                               self.numCoreNodes,
                               self.emqx_core_ins_type,
                               self.numLg,
                               self.loadgen_ins_type,
                               self.emqx_src_cmd))
        else:
            logging.warning("👍🏼  Will deploy %d %s EMQX and %d %s Loadgens\n get emqx src by %s "
                            % (self.numEmqx,
                               self.emqx_ins_type,
                               self.numLg,
                               self.loadgen_ins_type,
                               self.emqx_src_cmd))
        logging.warning(f"⚒  Image used to build EMQ X: {self.emqx_builder_image}")
        logging.warning(f"⚒  Command used to build EMQ X: `make {self.emqx_build_profile}'")

        if not self.enable_nginx:
            logging.warning("🔓  Will *not* deploy Nginx (SSL connection for EMQ X will be disabled)")

        if self.emqx_ebs_vol_size:
            logging.warning("💾  with extra vol %G  for EMQX" %
                            int(self.emqx_ebs_vol_size))

        if self.kafka_ebs_vol_size:
            logging.warning("💾  with extra vol %G  for Kafka, Kafka will be deployed" %
                            int(self.kafka_ebs_vol_size))

        logging.warning(f"💽  DB backend: {self.dbBackend}")
        if self.dbBackend == "rlog":
            numReplicants = self.numEmqx - self.numCoreNodes
            logging.warning(
                f"💽    with {numReplicants} replicant and {self.numCoreNodes} core node(s)")

        if self.enable_pulsar:
            logging.warning("💫  Will deploy Pulsar to EKS")

    @staticmethod
    def attach_ssm_policy(role):
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'))

    def attach_s3_policy(self, role):
        id = 's3-access-cluster-bucket'
        policy = self.s3_bucket_policy
        if not policy:
            # https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-arn-format.html
            resource = cdk.Arn.format(cdk.ArnComponents(service='s3',
                                                          account='',  # acc should not be set for s3 arn
                                                          region='',  # region should not be set for s3 arn
                                                          resource=self.s3_bucket_name,  # bucket name
                                                          resource_name=self.cluster_name+'*'
                                                          ), self)

            statement_all = iam.PolicyStatement(actions=['s3:*'],
                                                effect=iam.Effect.ALLOW,
                                                resources=[resource])
            statement_list = iam.PolicyStatement(actions=['s3:List*'],
                                                 effect=iam.Effect.ALLOW,
                                                 resources=['*'])

            policy = iam.Policy(self, id=id, statements=[
                                statement_all, statement_list])
            self.s3_bucket_policy = policy

        role.attach_inline_policy(policy)

    def setup_kafka(self):
        if not self.kafka_ebs_vol_size:
            self.kafka = None
            return

        role = IamRoleFis(self, id='emqx-kafka-fis-role')
        self.role_arn = role.role_arn
        # Kafka Internal Access
        kafka_sg = ec2.SecurityGroup(self, id='sg_kafka', vpc=self.vpc)
        kafka_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.all_traffic())
        kafka_sg.add_ingress_rule(self.sg, ec2.Port.all_traffic())
        self.kafka = msk.Cluster(self, id='kafka', cluster_name=self.cluster_name+'-kafka',
                                 kafka_version=msk.KafkaVersion.V2_6_0,
                                 ebs_storage_info=msk.EbsStorageInfo(
                                     volume_size=int(self.kafka_ebs_vol_size)),
                                 vpc=self.vpc, number_of_broker_nodes=1,
                                 vpc_subnets=ec2.SubnetSelection(
                                     subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, one_per_az=True),
                                 removal_policy=cdk.RemovalPolicy.DESTROY,
                                 security_groups=[kafka_sg],
                                 encryption_in_transit = msk.EncryptionInTransitConfig(
                                     client_broker=msk.ClientBrokerEncryption.TLS_PLAINTEXT)
                                 )

        if True:
            cmd_fis_network_loss_src = ControlCmd(self, 'fis-network-packet-loss-src',
                                         'fis-network-packet-loss-src.yaml', service='emqx')
            cmd_fis_network_latency_src = ControlCmd(self, 'fis-network-latency-src',
                                             'fis-network-latency-src.yaml', service='emqx')

            SsmDocExperiment(self, id='kafka-plaintext-pktloss-10',
                             name=cmd_fis_network_loss_src.phid_name,
                             desc='Kafka plaintext broker packet loss 10%',
                             doc_parms={'Interface': 'ens5',
                                        'Sources' : self.kafka.bootstrap_brokers,
                                        'LossPercent': '10',
                                        'DurationSeconds': '120'
                                        }
                             )

            SsmDocExperiment(self, id='kafka-plaintext-pktloss-100',
                             name=cmd_fis_network_loss_src.phid_name,
                             account = self.account,
                             desc='Kafka plaintext broker packet loss 100%',
                             doc_parms={'Interface': 'ens5',
                                        'Sources' : self.kafka.bootstrap_brokers,
                                        'LossPercent': '100',
                                        'DurationSeconds': '120'
                                        }
                             )

            SsmDocExperiment(self, id='kafka-plaintext-latency-200',
                             name=cmd_fis_network_latency_src.phid_name,
                             account = self.account,
                             desc='Kafka, latency inc 200ms',
                             doc_parms={'TrafficType':'ingress',
                                        'DurationSeconds': '120',
                                        'Sources' : self.kafka.bootstrap_brokers,
                                        'DelayMilliseconds' : '200',
                                        'JitterMilliseconds' : '10',
                                        'Interface':'ens5'}
                             )

    def setup_pulsar(self):
        if not self.enable_pulsar:
            return

        # https://github.com/apache/pulsar-helm-chart
        # https://pulsar.apache.org/docs/helm-deploy/
        # https://docs.aws.amazon.com/cdk/api/v1/python/aws_cdk.aws_eks/Cluster.html
        # https://docs.aws.amazon.com/cdk/api/v1/python/aws_cdk.aws_eks/HelmChart.html
        eks_cluster = eks.Cluster(
            self,
            id=self.cluster_name + "-pulsar",
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )],
            endpoint_access=eks.EndpointAccess.PRIVATE,
            version=eks.KubernetesVersion.V1_21,
        )
        nodegroup = eks_cluster.add_nodegroup_capacity(
            id=self.cluster_name + "-pulsar-nodegroup",
            capacity_type=eks.CapacityType.ON_DEMAND,
            min_size=1,
            desired_size=2,
            max_size=3,
            # disk_size=20,
            # force_update=True,
            instance_types=[
                ec2.InstanceType(instance_type_identifier="t3.medium"),
            ],
            remote_access=eks.NodegroupRemoteAccess(
                ssh_key_name=self.ssh_key,
            ),
        )
        nodegroup.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        # install cert-manager to enable tls self-signed certs
        # https://github.com/aws/aws-cdk/issues/8340#issuecomment-639372288
        # https://github.com/apache/pulsar/issues/14547
        CERT_MANAGER_VERSION = "v1.5.4"
        cert_manager_helm = eks_cluster.add_helm_chart(
            id=f"{self.cluster_name}-cert-manager-helm",
            chart="cert-manager",
            repository="https://charts.jetstack.io",
            release=f"{self.cluster_name}-cert-manager",
            create_namespace=True,
            namespace="cert-manager",
            version=CERT_MANAGER_VERSION,
            values={
                "installCRDs": True,
            },
            wait=True,
        )

        # pulsar helm values
        PULSAR_CHART_VERSION = "2.9.3"
        helm_values = {
            "monitoring": {
                "prometheus": False,
                "grafana": False,
            },
            "components": {
                "toolset": False,
                "functions": False,
                "autorecovery": False,
                "pulsar_manager": True,
            },
            "zookeeper": {
                "replicaCount": 1,
            },
            "bookkeeper": {
                "replicaCount": 1,
            },
            "proxy": {
                "replicaCount": 1,
            },
            "broker": {
                "replicaCount": 1,
                "configData": {
                    ## Enable `autoSkipNonRecoverableData` since bookkeeper is running
                    ## without persistence
                    "autoSkipNonRecoverableData": "true",
                    # storage settings
                    "managedLedgerDefaultEnsembleSize": "1",
                    "managedLedgerDefaultWriteQuorum": "1",
                    "managedLedgerDefaultAckQuorum": "1",
                },
            },
            # enable tls
            "tls": {
                "enabled": True,
                "proxy": {
                    "enabled": True,
                },
                "broker": {
                    "enabled": True,
                },
                "zookeeper": {
                    "enabled": True,
                },
            },
            # issue self signing certs
            "certs": {
                "internal_issuer": {
                    "enabled": True,
                    "apiVersion": "cert-manager.io/v1alpha2",
                    "type": "selfsigning",
                },
            },
        }
        release_name = f"{self.cluster_name}-pulsar-release"
        pulsar_helm = eks_cluster.add_helm_chart(
            id=f"{self.cluster_name}-pulsar-helm",
            chart="pulsar",
            repository="https://pulsar.apache.org/charts",
            release=release_name,
            create_namespace=True,
            namespace="pulsar",
            values=helm_values,
            version=PULSAR_CHART_VERSION,
        )
        # cert-manager CRDs must be installed before pulsar with TLS
        # is installed...
        pulsar_helm.node.add_dependency(cert_manager_helm)
        service_address = eks.KubernetesObjectValue(
            self, id="pulsar-service-ip",
            cluster=eks_cluster,
            object_type="service",
            object_name=release_name + "-proxy",
            object_namespace="pulsar",
            json_path=".status.loadBalancer.ingress[0].hostname",
        )
        cdk.CfnOutput(self, "Pulsar Proxy URL",
                       value=f"pulsar+ssl://{service_address.value}:6651")
        cdk.CfnOutput(self, "Pulsar Proxy URL command (run in bastion)",
                       value=f'kubectl -n pulsar get svc {release_name + "-proxy"} '
                              '-o=jsonpath="{.status.loadBalancer.ingress[0].hostname}"')
        self.pulsar_eks_cluster = eks_cluster


    def setup_efs(self):
        # New SG for EFS
        self.sg_efs_mt = ec2.SecurityGroup(self, "sg_efs_mt", vpc=self.vpc)
        self.sg_efs_mt.add_ingress_rule(
            peer=self.sg, connection=ec2.Port.all_traffic())

        fsid = 'shared-data' + self.cluster_name
        if isinstance(self.retain_efs, str) and self.retain_efs.startswith('fs-'):
            # reuse existing EFS
            fsid = self.retain_efs
            self.shared_efs = efs.FileSystem.from_file_system_attributes(self, id=fsid, security_group=self.sg_efs_mt,
                                                                         file_system_id=self.retain_efs)
            # we need to explicitly add the mount targets for all private subnets
            for (netid, net) in enumerate(self.vpc.private_subnets):
                cfn_mount_target = efs.CfnMountTarget(self, 'monitoring-mountpoint-%s' % netid,
                                                      file_system_id=self.shared_efs.file_system_id,
                                                      security_groups=[
                                                          self.sg_efs_mt.security_group_id],
                                                      subnet_id=net.subnet_id
                                                      )
        else:
            # Create new one with RemovalPolicy flag
            if self.retain_efs:
                remove_policy = cdk.RemovalPolicy.RETAIN
            else:
                remove_policy = cdk.RemovalPolicy.DESTROY
            self.shared_efs = efs.FileSystem(self, id=fsid, vpc=self.vpc,
                                             removal_policy=remove_policy,
                                             lifecycle_policy=efs.LifecyclePolicy.AFTER_14_DAYS,
                                             performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
                                             security_group=self.sg_efs_mt,
                                             )
