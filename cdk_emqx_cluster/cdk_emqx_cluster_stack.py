from aws_cdk import core as cdk

# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
#from aws_cdk import core
from aws_cdk import (core as cdk, aws_ec2 as ec2, aws_ecs as ecs,
                     core as core,
                     aws_logs as aws_logs,
                     aws_elasticloadbalancingv2 as elb,
                     aws_elasticloadbalancingv2_targets as target,
                     aws_route53 as r53,
                     aws_route53_targets as r53_targets,
                     aws_elasticloadbalancingv2 as elbv2,
                     aws_fis as fis,
                     aws_iam as iam,
                     aws_ecs_patterns as ecs_patterns)
from aws_cdk.core import Duration, CfnParameter
from base64 import b64encode
import sys
import logging

linux_ami = ec2.GenericLinuxImage({
    #"eu-west-1": "ami-06fd78dc2f0b69910", # ubuntu 18.04 latest
    "eu-west-1": "ami-09c60c18b634a5e00", # ubuntu 20.04 latest
    })

with open("./user_data/emqx_init.sh") as f:
    emqx_user_data = f.read()

with open("./user_data/loadgen_init.sh") as f:
    loadgen_user_data = f.read()

with open("./user_data/os_common.sh") as f:
    os_common_user_data = f.read()
    user_data_os_common = ec2.UserData.custom(os_common_user_data)

with open("./user_data/nginx.sh") as f:
    user_data_nginx = ec2.UserData.custom(f.read())

class CdkEmqxClusterStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        if self.node.try_get_context("tags"):
            self.user_defined_tags = self.node.try_get_context("tags").split(' ')
        else:
            self.user_defined_tags = None

        self.hosts = []

        # Read context params
        self.read_param()

        # Prepare infrastructure
        self.set_cluster_name()
        self.setup_ssh_key()
        self.setup_vpc()
        self.setup_sg()
        self.setup_r53()
        self.setup_lb()

        # Setup Bastion
        self.setup_bastion()

        # Create Application Services
        self.setup_emqx(self.numEmqx)
        self.setup_etcd()
        self.setup_loadgen(self.numLg)
        self.setup_monitoring(self.hosts)

        # setup Fis
        self.setup_fis()

        # Outputs
        self.cfn_outputs()


    #%% followings are internals
    def cfn_outputs(self):
        core.CfnOutput(self, "ClusterName",
                       value=self.cluster_name)
        core.CfnOutput(self, "Loadbalancer",
            value=self.nlb.load_balancer_dns_name)
        core.CfnOutput(self, "SSH Entrypoint",
                       value=self.bastion.instance_public_ip)
        core.CfnOutput(self, "Hosts are", value = '\n'.join(self.hosts))
        core.CfnOutput(self, "SSH Commands for Access",
                       value="ssh -A -l ec2-user %s -L8888:%s:80 -L 9999:%s:80 -L 13000:%s:3000"
                       % (self.bastion.instance_public_ip, self.nlb.load_balancer_dns_name, self.mon_lb, self.mon_lb)
                      )

    def setup_loadgen(self, N):
        vpc = self.vpc
        zone = self.int_zone
        sg = self.sg
        key = self.ssh_key
        target = self.nlb.load_balancer_dns_name

        for n in range(0, N):
            name = "loadgen-%d" % n
            bootScript = ec2.UserData.custom(loadgen_user_data)
            configIps = ec2.UserData.for_linux()
            configIps.add_commands("for x in $(seq 2 250); do ip addr add 192.168.%d.$x dev ens5; done" % n)
            runscript = ec2.UserData.for_linux()
            runscript.add_commands("""cat << EOF > /root/emqtt-bench/run.sh
            #!/bin/bash
            ulimit -n 1000000
            ipaddrs=$(ip addr |grep -o '192.*/32' | sed 's#/32##g' | paste -s -d , -)
            _build/default/bin/emqtt_bench sub -h %s -t "root/%%c/1/+/abc/#" -c 200000 --prefix "prefix%d" --ifaddr $ipaddrs -i 5
EOF
            """ % (target, n)
            )
            multipartUserData = ec2.MultipartUserData()
            configIps.add_commands("hostname %s" % name + self.domain)
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(user_data_os_common))
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(bootScript))
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(configIps))
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(runscript))
            lg_vm = ec2.Instance(self, id = name,
                                 instance_type=ec2.InstanceType(instance_type_identifier=self.loadgen_ins_type),
                                 machine_image=linux_ami,
                                 user_data = multipartUserData,
                                 security_group = sg,
                                 key_name=key,
                                 vpc = vpc,
                                 source_dest_check = False
            )

            ## add routes for traffic from loadgen
            i=1
            for net in vpc.private_subnets:
                net.add_route(id=name+str(i),
                              router_id = lg_vm.instance_id,
                              router_type = ec2.RouterType.INSTANCE,
                              destination_cidr_block = "192.168.%d.0/24" % n)
                i+=1

            dnsname = "%s%s" % (name, self.domain)
            r53.ARecord(self,
                        id = dnsname,
                        record_name = dnsname,
                        zone = zone,
                        target = r53.RecordTarget([lg_vm.instance_private_ip])
            )

            self.hosts.append(dnsname)

            if self.user_defined_tags:
                core.Tags.of(ins).add(*self.user_defined_tags)
            core.Tags.of(lg_vm).add('service', 'loadgen')


    def setup_monitoring(self, targets):
        vpc = self.vpc
        sg = self.sg
        nlb = self.nlb
        with open("./user_data/prometheus.yml") as f:
            prometheus_config = f.read()
            prometheus_config = prometheus_config % ','.join(['"%s:%d"' % (t,9100) for t in targets])

        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(9090), 'prometheus')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(9100), 'prometheus node exporter')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(9091), 'prometheus pushgateway')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(3000), 'grafana')

        cluster = ecs.Cluster(self, "Monitoring", vpc=vpc)
        task = ecs.FargateTaskDefinition(self,
                                         id = 'MonitorTask',
                                         cpu = 512,
                                         memory_limit_mib = 2048
                                         #volumes = [ecs.Volume(name = cfgVolName)]
               )
        task.add_volume(name = 'prom_config')
        c_config = task.add_container('config-prometheus',
                                       image=ecs.ContainerImage.from_registry('bash'),
                                       essential=False,
                                       logging = ecs.LogDriver.aws_logs(stream_prefix="mon_config_prometheus",
                                                                        log_retention = aws_logs.RetentionDays.ONE_DAY
                                       ),
                                       command = [ "-c",
                                                   "echo $DATA | base64 -d - | tee /tmp/private/prometheus.yml"
                                                 ],
                                       environment = {'DATA' : cdk.Fn.base64(prometheus_config)}

        )
        c_config.add_mount_points(ecs.MountPoint(read_only = False, container_path='/tmp/private', source_volume='prom_config'))
        c_prometheus = task.add_container('prometheus',
                                          essential=False,
                                          image=ecs.ContainerImage.from_registry('prom/prometheus'),
                                          port_mappings = [ecs.PortMapping(container_port=9090)],
                                          command = [
                                              "--config.file=/etc/prometheus/private/prometheus.yml",
                                              "--storage.tsdb.path=/prometheus",
                                              "--web.console.libraries=/usr/share/prometheus/console_libraries",
                                              "--web.console.templates=/usr/share/prometheus/consoles"
                                          ],
                                          logging = ecs.LogDriver.aws_logs(stream_prefix="mon_prometheus",
                                                                        log_retention = aws_logs.RetentionDays.ONE_DAY
                                          ),

        )
        c_prometheus.add_mount_points(ecs.MountPoint(read_only = False, container_path='/etc/prometheus/private', source_volume='prom_config'))
        c_prometheus.add_container_dependencies(ecs.ContainerDependency(container=c_config, condition=ecs.ContainerDependencyCondition.COMPLETE))


        c_pushgateway = task.add_container('pushgateway',
                                           essential=False,
                                          image=ecs.ContainerImage.from_registry('prom/pushgateway'),
                                          port_mappings = [ecs.PortMapping(container_port=9091)]
        )

        c_grafana = task.add_container('grafana',
                                       essential=True,
                                       image=ecs.ContainerImage.from_registry('grafana/grafana'),
                                       port_mappings = [ecs.PortMapping(container_port=3000)]
        )

        service = ecs.FargateService(self, "EMQXMonitoring",
                                     security_group = self.sg,
                                     cluster = cluster,
                                     task_definition = task,
                                     desired_count = 1,
                                     assign_public_ip = True

        )

        listenerGrafana = nlb.add_listener('grafana', port = 3000);
        listenerPrometheus = nlb.add_listener('prometheus', port = 9090);
        listenerPushGateway = nlb.add_listener('pushgateway', port = 9091);

        listenerGrafana.add_targets(id = 'grafana', port=3000, targets = [service.load_balancer_target(
            container_name="grafana",
            container_port=3000
        )])
        listenerPrometheus.add_targets(id = 'prometheus', port=9090, targets=[service.load_balancer_target(
            container_name="prometheus",
            container_port=9090
        )])

        listenerPushGateway.add_targets(id = 'pushgateway', port=9091, targets=[service.load_balancer_target(
            container_name="pushgateway",
            container_port=9091
        )]) ,

        self.mon_lb = self.loadbalancer_dnsname
        core.CfnOutput(self, "Monitoring Grafana",
                       value = "%s:%d" % (self.mon_lb, 3000))
        core.CfnOutput(self, "Monitoring Prometheus",
                       value = "%s:%d" % (self.mon_lb, 9090))


    def setup_emqx(self, N):
        vpc = self.vpc
        zone = self.int_zone
        sg = self.sg
        key = self.ssh_key
        nlb = self.nlb
        self.emqx_vms = []


        for n in range(0, N):
            name = "emqx-%d" % n
            dnsname = name + self.domain
            if self.emqx_ebs_vol_size and int(self.emqx_ebs_vol_size) > 0:
                blockdevs = [ec2.BlockDevice(device_name = '/dev/xvda', volume = ec2.BlockDeviceVolume.ebs(int(self.emqx_ebs_vol_size)))]
            else:
                blockdevs = []
            userdata_hostname = ec2.UserData.for_linux()
            userdata_hostname.add_commands("hostname %s" % dnsname)
            userdata_init = ec2.UserData.for_linux()
            userdata_init.add_commands('cd /root')
            userdata_init.add_commands(self.emqx_src_cmd)
            userdata_init.add_commands(emqx_user_data)
            multipartUserData = ec2.MultipartUserData()
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(userdata_hostname))
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(user_data_os_common))
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(userdata_init))
            multipartUserData.add_part(ec2.MultipartBody.from_user_data(user_data_nginx))

            vm = ec2.Instance(self, id = name,
                              instance_type = ec2.InstanceType(instance_type_identifier=self.emqx_ins_type),
                              block_devices = blockdevs,
                              machine_image = linux_ami,
                              user_data = multipartUserData,
                              security_group = sg,
                              key_name = key,
                              vpc = vpc,
                              vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE),
            )

            self.emqx_vms.append(vm)


            r53.ARecord(self, id = dnsname,
                        record_name = dnsname,
                        zone = zone,
                        target = r53.RecordTarget([vm.instance_private_ip])
            )
            self.hosts.append(dnsname)

            # tagging
            if self.user_defined_tags:
                core.Tags.of(vm).add(*self.user_defined_tags)
            core.Tags.of(vm).add('service', 'emqx')

            # tag ins for chaos testing with AWS FIS
            if self.is_chaos_ready:
                core.Tags.of(vm).add('chaos_ready', 'true')

        # Add LB endpoints
        listener = nlb.add_listener("port1883", port=1883)
        listenerTLS = nlb.add_listener("port8883", port=8883) # TLS, emqx terminataion
        listenerTLSNginx = nlb.add_listener("port18883", port=18883)
        listenerQuic = nlb.add_listener("port14567", port=14567, protocol=elbv2.Protocol.UDP)
        listenerUI = nlb.add_listener("port80", port=80)

        listener.add_targets('ec2',
                             port=1883,
                             targets=
                                 [ target.InstanceTarget(x)
                                   for x in self.emqx_vms])
        # @todo we need ssl terminataion
        listenerUI.add_targets('ec2',
                               port=18083,
                               targets=[ target.InstanceTarget(x)
                                   for x in self.emqx_vms])

        listenerQuic.add_targets('ec2',
                                 port=14567,
                                 protocol=elbv2.Protocol.UDP,
                                 targets=[ target.InstanceTarget(x)
                                   for x in self.emqx_vms])

        listenerTLS.add_targets('ec2',
                                port=8883,
                                targets=[ target.InstanceTarget(x)
                                   for x in self.emqx_vms])
        listenerTLSNginx.add_targets('ec2',
                               port=18883,
                               targets=[ target.InstanceTarget(x)
                                   for x in self.emqx_vms])

    def setup_etcd(self):
        for n in range(0, 3):
            vpc = self.vpc
            zone = self.int_zone
            sg = self.sg
            key = self.ssh_key
            # cdk bug?
            (cloud_user_data, )= ec2.UserData.for_linux(),
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
                                         'systemctl restart etcd'
            )
            ins = ec2.Instance(self, id = "etsd.%d" % n,
                               instance_type=ec2.InstanceType(instance_type_identifier="t3a.nano"),
                               machine_image=linux_ami,
                               user_data=cloud_user_data,
                               security_group = sg,
                               key_name=key,
                               vpc = vpc
            )
            dnsname = "etcd%d" % n + self.domain
            r53.ARecord(self, id = dnsname,
                        record_name = dnsname,
                        zone = zone,
                        target = r53.RecordTarget([ins.instance_private_ip])
            )
            self.hosts.append(dnsname)

            if self.user_defined_tags:
                core.Tags.of(ins).add(*self.user_defined_tags)
            core.Tags.of(ins).add('service', 'etcd')

    def setup_vpc(self):
        vpc = ec2.Vpc(self, "VPC EMQX %s" % self.cluster_name,
            max_azs=1,
            cidr="10.10.0.0/16",
            # configuration will create 3 groups in 1 AZs = 3 subnets.
            subnet_configuration=[ec2.SubnetConfiguration(
                subnet_type=ec2.SubnetType.PUBLIC,
                name="Public",
                cidr_mask=24
            ), ec2.SubnetConfiguration(
                subnet_type=ec2.SubnetType.PRIVATE,
                name="Private",
                cidr_mask=24
            )],
            nat_gateways = 1
            )
        self.vpc = vpc

    def set_cluster_name(self):
        self.cluster_name = core.Stack.of(self).stack_name
        if not self.cluster_name:
            sys.exit("Cannot define cluster_name")
        self.domain = ".int.%s" % self.cluster_name

    def setup_r53(self):
        self.r53_zone_name = "%s_emqx_hosted_zone" % self.cluster_name
        self.int_zone = r53.PrivateHostedZone(self, self.r53_zone_name,
                                         zone_name = "int.%s" % self.cluster_name,
                                         vpc = self.vpc
        )

    def setup_ssh_key(self):
        self.ssh_key = CfnParameter(self, "ssh key",
             type="String", default="key_ireland",
             description="Specify your SSH key").value_as_string


    def setup_sg(self):
        """
        Setup security group, one for EC2 instances, because I am lazy.
        """
        sg = ec2.SecurityGroup(self, id = 'sg_int', vpc = self.vpc)
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), 'SSH from anywhere')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(1883), 'MQTT TCP Port')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8883), 'MQTT TCP/TLS Port')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(18883), 'NGINX')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.udp(14567), 'MQTT Quic Port')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(18083), 'WEB UI')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(4369), 'EMQX dist port 1')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(4370), 'EMQX dist port 2')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5369), 'EMQX gen_rpc dist port 1')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5370), 'EMQX gen_rpc dist port 2')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8081), 'EMQX dashboard')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(2379), 'ETCD client port')
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(2380), 'ETCD peer port')
        self.sg = sg

    def setup_bastion(self):
        """
        This is a SSH proxy/middleman sit between Internet and VPC.
        """
        bastion = ec2.BastionHostLinux(self, "Bastion",
                                       vpc=self.vpc,
                                       subnet_selection=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
                                       instance_name="BastionHostLinux %s" % self.cluster_name,
                                       instance_type=ec2.InstanceType(instance_type_identifier="t3.nano"))

        bastion.instance.instance.add_property_override("KeyName", self.ssh_key)
        bastion.connections.allow_from_any_ipv4(ec2.Port.tcp(22), "Internet access SSH")
        self.bastion = bastion

    def setup_lb(self):
        """
        Setup network load balancer
        """
        self.loadbalancer_dnsname='lb' + self.domain
        nlb = elb.NetworkLoadBalancer(self, "emqx-elb",
                                      vpc = self.vpc,
                                      internet_facing = False,
                                      cross_zone_enabled = True,
                                      load_balancer_name="emqx-nlb-%s" % self.cluster_name)
        r53.ARecord(self, "AliasRecord",
                    zone = self.int_zone,
                    record_name = self.loadbalancer_dnsname,
                    target = r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(nlb))
                    )
        self.nlb = nlb

    def read_param(self):
        # CHAOS_READY, if true, cluster is chaos ready and able to accept chaos tests.
        self.is_chaos_ready = bool(self.node.try_get_context('chaos'))

        # EMQX Instance Type
        # https://aws.amazon.com/ec2/instance-types/
        # suggested m5.2xlarge
        self.emqx_ins_type = self.node.try_get_context('emqx_ins_type') or 't3a.small'

        # Number of EMQXs
        self.numEmqx = int(self.node.try_get_context('emqx_n') or 2 )

        # LOADGEN Instance Type
        # suggested m5n.xlarge
        self.loadgen_ins_type = self.node.try_get_context('loadgen_ins_type') or 't3a.micro'

        # Number of LOADGENS
        self.numLg = int(self.node.try_get_context('lg_n') or 1 )

        # Extra EBS vol size for EMQX DATA per EMQX Instance
        self.emqx_ebs_vol_size = self.node.try_get_context('emqx_ebs')

        # EMQX source
        self.emqx_src_cmd = self.node.try_get_context('emqx_src') or "git clone https://github.com/emqx/emqx"

        logging.warning("👍🏼  Will deploy %d %s EMQX and %d %s Loadgens\n get emqx src by %s "
            % (self.numEmqx, self.emqx_ins_type, self.numLg, self.loadgen_ins_type, self.emqx_src_cmd))
        if self.emqx_ebs_vol_size:
            logging.warning("💾  with extra vol %G  for EMQX" % int(self.emqx_ebs_vol_size))


    def setup_fis(self):
        """
        Setup Fis
         - create a chaos experiment template
         - create role for it
        you can trigger the chaos experiment by:
         aws fis start-experiment --experiment-template-id=EXT4ETdyMGaZ4RN8
        """
        if not self.is_chaos_ready:
            return
        policy = iam.PolicyDocument()
        policy.add_statements(
            iam.PolicyStatement(
                sid = 'AllowFISExperimentRoleEC2ReadOnly',
                actions =  ['ec2:DescribeInstances'],
                resources = ["*"],
                effect = iam.Effect.ALLOW
            ),
            iam.PolicyStatement(
                sid = 'AllowFISExperimentRoleEC2Actions',
                actions =  ['ec2:RebootInstances',
                            'ec2:StopInstances',
                            'ec2:StartInstances',
                            'ec2:TerminateInstances'],
                resources = ['arn:aws:ec2:*:*:instance/*'],
                effect = iam.Effect.ALLOW
            ),
            iam.PolicyStatement(
                sid = 'AllowFISExperimentRoleSpotInstanceActions',
                actions =  ['ec2:RebootInstances',
                            'ec2:StopInstances',
                            'ec2:StartInstances',
                            'ec2:TerminateInstances'],
                resources = ['arn:aws:ec2:*:*:instance/*'],
                effect = iam.Effect.ALLOW
            )
        )
        fis_role = iam.Role(self, id = 'emqx-fis-role',
                        assumed_by = iam.ServicePrincipal('fis.amazonaws.com'),
                        inline_policies = [policy]
                        ),
        fis.CfnExperimentTemplate(self, id = 'emqx-node-shutdown',
                            description = 'EMQX node shutdown',
                            role_arn = fis_role[0].role_arn,
                            stop_conditions = [fis.CfnExperimentTemplate.ExperimentTemplateStopConditionProperty(source = "none")],
                            tags = {'domain' : self.domain},
                            targets = {'target-1' : fis.CfnExperimentTemplate.ExperimentTemplateTargetProperty(
                                resource_type = 'aws:ec2:instance',
                                selection_mode = 'COUNT(1)',
                                resource_tags = {'chaos_ready': 'true', 'domain': self.domain}
                            )},
                            actions = {'action-1' : fis.CfnExperimentTemplate.ExperimentTemplateActionProperty(
                                action_id='aws:ec2:stop-instances',
                                parameters={'startInstancesAfterDuration': 'PT1M'},
                                targets = {'Instances': 'target-1'} # reference to targets
                                )}
        )
