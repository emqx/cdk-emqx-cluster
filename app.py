#!/usr/bin/env python3
import os
import sys

from aws_cdk import App

from cdk_emqx_cluster.cdk_emqx_cluster_stack import CdkEmqxClusterStack
from cdk_emqx_cluster.cdk_chaos_test import CdkChaosTest


app = App()
stack_name = os.getenv('CDK_EMQX_CLUSTERNAME')
if not stack_name:
    sys.exit("env CDK_EMQX_CLUSTERNAME is not set")

emqx = CdkEmqxClusterStack(app, "CdkEmqxClusterStack", stack_name = stack_name
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.

    #env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */

    #env=cdk.Environment(account='123456789012', region='us-east-1'),

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    )

# Stack for running chaos test including SSM and FIS resources
CdkChaosTest(app, "CDKChaosTest", stack_name = stack_name + 'chaostest'
             , target_stack = emqx
             , cluster_name = stack_name)


app.synth()
