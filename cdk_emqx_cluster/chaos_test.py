
from aws_cdk import core as cdk

# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
# from aws_cdk import core
from aws_cdk import (core as cdk, aws_ec2 as ec2, aws_ecs as ecs,
                     core as core,
                     aws_logs as aws_logs,
                     aws_fis as fis,
                     aws_iam as iam,
                     aws_ssm as ssm
                     )
from aws_cdk.core import Duration, CfnParameter
from base64 import b64encode
import sys
import logging
import yaml
import json


class CdkChaosTest(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, cluster_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.cluster_name = cluster_name
        role = IamRoleFis(self, id='emqx-fis-role')
        self.role_arn = role.role_arn
        self.exps = [
            # note, ec2 instances must be tagged with 'chaos_ready' to get tested
            CdkExpirement(self, id='emqx-node-shutdown', name='emqx-node-shutdown',
                          description='emqx node shutdown',

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
                          )

        ]

        self.cmds = [
            ControlCmd(self, 'start_traffic', 'start_traffic.yaml', service = 'loadgen'),
            ControlCmd(self, 'collect_logs', 'collect_logs.yaml', service = 'emqx')
        ]

class ControlCmd(ssm.CfnDocument):
    def __init__(self, scope: cdk.Construct, construct_id: str, doc_name: str, service: str, **kwargs) -> None:
        content = yaml.safe_load(open("./ssm_docs/" + doc_name).read())
        super().__init__(scope, construct_id,
                         tags = [core.CfnTag(key = 'cluster', value = scope.cluster_name),
                                 core.CfnTag(key = 'service', value = service),
                                 core.CfnTag(key = 'cmd', value = construct_id)
                                ],
                         document_format = 'YAML',
                         document_type = 'Command',
                         content = content,
                         **kwargs)

class CdkExpirement(fis.CfnExperimentTemplate):
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
        return [policy_ec2, policy_ssm]
