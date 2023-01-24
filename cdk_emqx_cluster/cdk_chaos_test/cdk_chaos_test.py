import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (aws_ec2 as ec2, aws_ecs as ecs,
                     aws_logs as aws_logs,
                     aws_fis as fis,
                     aws_iam as iam,
                     aws_ssm as ssm,
                     aws_events as events,
                     aws_events_targets as targets,
                     aws_lambda as _lambda,
                     aws_stepfunctions as sfn,
                     aws_stepfunctions_tasks as tasks
                     )

from aws_cdk import Duration, CfnParameter
from base64 import b64encode
import sys
import logging
import yaml
import json


class CdkChaosTest(cdk.Stack):
    """
    refs:
    https://docs.aws.amazon.com/fis/latest/userguide/fis-actions-reference.html
    https://docs.aws.amazon.com/fis/latest/userguide/actions-ssm-agent.html
    """
    def __init__(self, scope: Construct, construct_id: str, cluster_name: str,
                 target_stack: cdk.Stack(), **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.cluster_name = cluster_name
        self.chaos_lambdas=dict()
        role = IamRoleFis(self, id='emqx-fis-role')
        self.role_arn = role.role_arn
        self.exps = [
            # note, ec2 instances must be tagged with 'chaos_ready' to get tested
            #
            # * NODE SHUTDOWN
            CdkExperiment(self, id='emqx-node-shutdown', name='emqx-node-shutdown',
                          description='EMQX: node shutdown',

                          # targets for faults injections
                          targets={'targets-emqx': fis.CfnExperimentTemplate.ExperimentTemplateTargetProperty(
                              resource_type='aws:ec2:instance',
                              selection_mode='COUNT(1)',
                              resource_tags={'chaos_ready': 'true', 'cluster': self.cluster_name})
                          },

                          # actions for faults injections
                          actions={
                              'action-1': fis.CfnExperimentTemplate.ExperimentTemplateActionProperty(
                                  action_id='aws:ec2:stop-instances',
                                  parameters={
                                            'startInstancesAfterDuration': 'PT1M'},
                                  # reference to targets
                                  targets={
                                      'Instances': 'targets-emqx'},
                              )

                          }
                          ),
            # * HIGH CPU LOAD 80%
            SsmDocExperiment(self, id='emqx-high-cpu-80', name='AWSFIS-Run-CPU-Stress',
                             desc='EMQX: CPU Stress 80% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'LoadPercent': '80'}),

            # * HIGH CPU LOAD 100%
            SsmDocExperiment(self, id='emqx-high-cpu-100', name='AWSFIS-Run-CPU-Stress',
                             desc='EMQX: CPU Stress 100% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'LoadPercent': '100'}),

            # * IO Stress
            SsmDocExperiment(self, id='emqx-high-io-80', name='AWSFIS-Run-IO-Stress',
                             desc='EMQX: IOStress 80% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'Percent': '80'}),

            # * IO Stress 100%
            SsmDocExperiment(self, id='emqx-high-io-100', name='AWSFIS-Run-IO-Stress',
                             desc='EMQX: IOStress 100% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'Percent': '100'}),

            # * Kill emqx Process
            SsmDocExperiment(self, id='emqx-kill-proc', name='AWSFIS-Run-Kill-Process',
                             desc='EMQX: Kill emqx Process for 2mins',
                             doc_parms={'ProcessName': 'beam.smp', 'Signal': 'SIGKILL'}),
            # * Mem Stress
            SsmDocExperiment(self, id='emqx-high-mem-80', name='AWSFIS-Run-Memory-Stress',
                             desc='EMQX: Mem: 80% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'Percent': '80'}),

            SsmDocExperiment(self, id='emqx-high-mem-95', name='AWSFIS-Run-Memory-Stress',
                             desc='EMQX: Mem: 95% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'Percent': '95'}),

            SsmDocExperiment(self, id='emqx-high-mem-100', name='AWSFIS-Run-Memory-Stress',
                             desc='EMQX: Mem: 100% for 2mins',
                             doc_parms={'DurationSeconds': '120', 'Percent': '100'}),

            # * Network Blackhole
            SsmDocExperiment(self, id='emqx-distport-blackhole', name='AWSFIS-Run-Network-Blackhole-Port',
                             desc='EMQX: Drop distport inbond traffic for 2mins',
                             doc_parms={'DurationSeconds': '120', 'Port': '4370', 'Protocol' : 'tcp', 'TrafficType':'ingress'}),

            # * Network Latency
            SsmDocExperiment(self, id='emqx-latency-200ms', name='AWSFIS-Run-Network-Latency',
                             desc='EMQX: NET Egress latency 200ms ',
                             doc_parms={'DurationSeconds': '120', 'DelayMilliseconds': '200', 'Interface':'ens5'}),

            # * Packet Loss
            SsmDocExperiment(self, id='emqx-packet-loss-10', name='AWSFIS-Run-Network-Packet-Loss',
                             desc='EMQX: NET, 10% egress Packet Lost for 2mins',
                             doc_parms={'DurationSeconds': '120', 'LossPercent': '10', 'Interface':'ens5'}), # ubuntu nif name

            SsmDocExperiment(self, id='emqx-packet-loss-100', name='AWSFIS-Run-Network-Packet-Loss',
                             desc='EMQX: NET, 100% egress Packet Lost for 2mins',
                             doc_parms={'DurationSeconds': '120', 'LossPercent': '100', 'Interface':'ens5'}) , # ubuntu nif name

        ]

        self.cmds = [
            ControlCmd(self, 'start_traffic',
                       'start_traffic.yaml', service='loadgen'),
            ControlCmd(self, 'collect_logs',
                       'collect_logs.yaml', service='emqx'),
            ControlCmd(self, 'stop_traffic',
                       'stop_traffic.yaml', service='loadgen')
        ]

        self.create_chaos_lambdas(vpc=target_stack.vpc)
        self.create_tasks()

    def create_tasks(self):
        traffic_sub_bg={"Host": "dummy", "Command":["sub"],"Prefix":["cdkS1"],"Topic":["root/%c/1/+/abc/#"],"Clients":["200000"],"Interval":["200"]}
        traffic_pub={"Host": "dummy", "Command":["pub"],"Prefix":["cdkP1"],"Topic":["t1"],"Clients":["200000"],"Interval":["200"], "PubInterval":["1000"]}
        traffic_sub={"Host": "dummy", "Command":["sub"],"Prefix":["cdkS2"],"Topic":["t1"],"Clients":["200"],"Interval":["200"]}

        job_success = sfn.Succeed(self, "Test complete and success")

        s_stop_traffic = ExecStepfun(self, 'Stop traffic','stop_traffic')
        s_start_traffic_sub = ExecStepfun(self, 'Start traffic sub', 'start_traffic',
                                                   parameters={'traffic_args': traffic_sub})
        s_start_traffic_pub = ExecStepfun(self, 'Start traffic pub', 'start_traffic',
                                                   parameters={'traffic_args': traffic_pub})
        s_start_traffic_sub_bg = ExecStepfun(self, 'Start traffic BG', 'start_traffic',
                                                       parameters={'traffic_args': traffic_sub_bg})
        s_inject_fault = ExecStepfun(self, 'Inject fault', 'inject_fault', check_delay_s=120)
        s_check_stable_traffic = tasks.LambdaInvoke(self, "Check Stable Traffic",
                                                    lambda_function=self.chaos_lambdas['check_traffic'],
                                                    payload=sfn.TaskInput.from_object({'period': '5m'}),
                                                    result_path=sfn.JsonPath.DISCARD
                                                    )
        s_check_recovery_traffic = tasks.LambdaInvoke(self, "Check Recovery Traffic",
                                                      lambda_function=self.chaos_lambdas['check_traffic'],
                                                      payload=sfn.TaskInput.from_object({'period': '5m'}),
                                                      result_path=sfn.JsonPath.DISCARD
                                                      )
        wait_stable = sfn.Wait(self, "Wait for traffic stable",
                               time=sfn.WaitTime.duration(cdk.Duration.seconds(300)))

        wait_recover = sfn.Wait(self, "Wait for recover",
                               time=sfn.WaitTime.duration(cdk.Duration.seconds(300)))

        definition = s_stop_traffic \
            .next(s_start_traffic_sub) \
            .next(s_start_traffic_pub) \
            .next(s_start_traffic_sub_bg) \
            .next(wait_stable) \
            .next(s_check_stable_traffic) \
            .next(s_inject_fault) \
            .next(wait_recover) \
            .next(s_check_recovery_traffic) \
            .next(job_success)

        sfn.StateMachine(self, "Run one chaos test",
                         state_machine_name=f"{self.cluster_name}-chaostest",
                         definition=definition
                         )

    def create_chaos_lambdas(self, vpc: ec2.Vpc):
        role=None
        sgs=[ec2.SecurityGroup(self, 'chaos-lambda-sg', vpc=vpc)]
        for ln in ['start_traffic',
                   'stop_traffic',
                   'poll_result',
                   'check_traffic',
                   'inject_fault']:
            self.chaos_lambdas[ln] = ChaosLambda(self, ln, vpc=vpc, role=role, security_groups=sgs,
                                                 environment={'cluster_name': cdk.Stack.of(self).cluster_name}
                                                 )
            role=self.chaos_lambdas[ln].role

        role.add_to_policy(iam.PolicyStatement(actions=['ssm:List*',
                                                        'ssm:SendCommand',
                                                        'fis:ListExperimentTemplates',
                                                        'fis:Get*',
                                                        'fis:StartExperiment',
                                                        ],
                                               effect=iam.Effect.ALLOW,
                                               resources=['*']))

class ChaosLambda(_lambda.Function):
    def __init__(self, scope: Construct, name: str, **kwargs) -> None:
        super().__init__(scope, 'lambda_'+name,
                         runtime=_lambda.Runtime.PYTHON_3_7,
                         code=_lambda.Code.from_asset('lambda'),
                         handler='chaos.handler_'+name,
                         **kwargs
                         )


class ControlCmd(ssm.CfnDocument):
    def __init__(self, scope: Construct, construct_id: str, doc_name: str, service: str, **kwargs) -> None:
        content = yaml.safe_load(open("./ssm_docs/" + doc_name).read())
        super().__init__(scope, construct_id,
                         tags=[cdk.CfnTag(key='cluster', value=scope.cluster_name),
                               cdk.CfnTag(key='service', value=service),
                               cdk.CfnTag(key='cmd', value=construct_id)
                               ],
                         document_format='YAML',
                         document_type='Command',
                         content=content,
                         **kwargs)
        # AWS limitation we have to override the physical id
        self.phid_name='%s-%s'%(scope.cluster_name, construct_id)
        self.add_property_override('Name', self.phid_name)

class CdkExperiment(fis.CfnExperimentTemplate):
    """
    Wrap ExperimentTemplate in a Stack
    note, to *save costs* avoid long during actions
    """

    def __init__(self, scope, name, **kwargs):
        super().__init__(scope,
                         stop_conditions=[
                             fis.CfnExperimentTemplate.ExperimentTemplateStopConditionProperty(source="none")],
                         tags={'cluster': scope.cluster_name,
                               'fault_name': name},
                         role_arn=scope.role_arn,
                         **kwargs)


class SsmDocExperiment(CdkExperiment):
    """ use 'aws ssm list-documents' to find all the available docs (AWS provides)"""
    def __init__(self, scope: Construct, id: str, name:str, doc_parms : dict, desc:str, account='', doc_arn = None) -> None:
        if not doc_arn:
            doc_arn = cdk.Arn.format(cdk.ArnComponents(service='ssm',
                                                         resource='document',
                                                         account=account,
                                                         resource_name=name
                                                         ), scope)
        self.doc_arn = doc_arn,
        super().__init__(scope, id=id, name=id,
                          description=desc,
                          # targets for faults injections, we pick only one
                          targets={'targets-emqx': fis.CfnExperimentTemplate.ExperimentTemplateTargetProperty(
                              resource_type='aws:ec2:instance',
                              selection_mode='COUNT(1)',
                              resource_tags={'chaos_ready': 'true', 'cluster': scope.cluster_name})
                          },

                          # actions for faults injections
                          actions={
                              'action-1': fis.CfnExperimentTemplate.ExperimentTemplateActionProperty(
                                  action_id='aws:ssm:send-command',
                                  parameters={ 'documentArn': doc_arn,
                                               'documentParameters': json.dumps(doc_parms),
                                               'duration' : 'PT2M'
                                              },
                                  # reference to targets
                                  targets={
                                      'Instances': 'targets-emqx'},
                              )
                          }
                          )

class IamRoleFis(iam.Role):
    def __init__(self, scope, **kwargs):
        super().__init__(scope,
                         inline_policies=self.policies(),
                         assumed_by=iam.ServicePrincipal(
                             'fis.amazonaws.com'), **kwargs)

    @ staticmethod
    def policies():
        """
        Policies for the FIS role.
        """
        # https://docs.aws.amazon.com/fis/latest/userguide/getting-started-iam-service-role.html
        ec2PolicyJson = """
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowFISExperimentRoleEC2ReadOnly",
                        "Effect": "Allow",
                        "Action": [
                            "ec2:DescribeInstances"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Sid": "AllowFISExperimentRoleEC2Actions",
                        "Effect": "Allow",
                        "Action": [
                            "ec2:RebootInstances",
                            "ec2:StopInstances",
                            "ec2:StartInstances",
                            "ec2:TerminateInstances"
                        ],
                        "Resource": "arn:aws:ec2:*:*:instance/*"
                    },
                    {
                        "Sid": "AllowFISExperimentRoleSpotInstanceActions",
                        "Effect": "Allow",
                        "Action": [
                            "ec2:SendSpotInstanceInterruptions"
                        ],
                        "Resource": "arn:aws:ec2:*:*:instance/*"
                    }
                ]
            }
            """
        ssmPolicyJson = """
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowFISExperimentRoleSSMReadOnly",
                        "Effect": "Allow",
                        "Action": [
                            "ec2:DescribeInstances",
                            "ssm:GetAutomationExecution",
                            "ssm:ListCommands"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Sid": "AllowFISExperimentRoleSSMSendCommand",
                        "Effect": "Allow",
                        "Action": [
                            "ssm:SendCommand"
                        ],
                        "Resource": [
                            "arn:aws:ec2:*:*:instance/*",
                            "arn:aws:ssm:*:*:document/*"
                        ]
                    },
                    {
                        "Sid": "AllowFISExperimentRoleSSMCancelCommand",
                        "Effect": "Allow",
                        "Action": [
                            "ssm:CancelCommand"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Sid": "AllowFISExperimentRoleSSMAutomation",
                        "Effect": "Allow",
                        "Action": [
                            "ssm:StartAutomationExecution",
                            "ssm:StopAutomationExecution"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Sid": "AllowFISExperimentRoleSSMAutomationPassRole",
                        "Effect": "Allow",
                        "Action": [
                            "iam:PassRole"
                        ],
                        "Resource": "arn:aws:iam::123456789012:role/my-automation-role"
                    }
                ]
            }
            """
        policy_ssm = iam.PolicyDocument.from_json(
            json.loads(ssmPolicyJson))
        policy_ec2 = iam.PolicyDocument.from_json(
            json.loads(ec2PolicyJson))
        return {
            "iam_role_fis_ec2": policy_ec2,
            "iam_role_fis_ssm": policy_ssm,
        }


class CtrlTask(sfn.StateMachine):
    def __init__(self, scope: Construct, name: str, lambda_fun: _lambda.Function,
                 parameters:dict=None, check_delay_s=3, retry_interval_sec=5, retry_max=100
                 ):
        init = sfn.Pass(scope, f"set param for {name}", parameters=parameters)
        start = tasks.LambdaInvoke(scope, 'task-step-'+name,
                                   lambda_function=lambda_fun)

        check = tasks.LambdaInvoke(scope, f"Check result of {name}",
                                   lambda_function=scope.chaos_lambdas['poll_result']
                                  )
        check.add_retry(errors=['Retry'], interval=cdk.Duration.seconds(retry_interval_sec),
                        max_attempts=retry_max)

        check_delay = sfn.Wait(scope, f"Delay before check {name}",
                               time=sfn.WaitTime.duration(cdk.Duration.seconds(check_delay_s))
                               )
        definition = init.next(start)\
                         .next(check_delay) \
                         .next(check) \
                         .next(sfn.Succeed(scope, name+' Success'))

        super().__init__(scope, id="task-"+name, definition=definition)
        return None


class ExecStepfun(tasks.StepFunctionsStartExecution):
    def __init__(self, scope: Construct, name: str, lambda_name: str, **kwargs) -> None:
        stm = CtrlTask(scope, name, scope.chaos_lambdas[lambda_name], **kwargs)
        super().__init__(scope, f'Call {name}',
                         state_machine=stm,
                         integration_pattern=sfn.IntegrationPattern.RUN_JOB,
                         result_path=sfn.JsonPath.DISCARD,
                         )
        return None
