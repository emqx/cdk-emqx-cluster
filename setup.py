import setuptools


with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="cdk_emqx_cluster",
    version="0.0.1",

    description="An empty CDK Python app",
    long_description=long_description,
    long_description_content_type="text/markdown",

    author="author",

    package_dir={"": "cdk_emqx_cluster"},
    packages=setuptools.find_packages(where="cdk_emqx_cluster"),

    install_requires=[
        "aws-cdk.aws-ec2==1.134.0",
        "aws-cdk.core==1.134.0",
        "aws-cdk.aws-ecs==1.134.0",
        "aws-cdk.aws-ecs-patterns==1.134.0",
        "aws-cdk.aws-elasticloadbalancingv2==1.134.0",
        "aws-cdk.aws-elasticloadbalancingv2-targets==1.134.0",
        "aws-cdk.aws-logs==1.134.0",
        "aws-cdk.aws-route53==1.134.0",
        "aws-cdk.aws-fis==1.134.0",
        "aws-cdk.aws-iam==1.134.0",
        "aws-cdk.aws-ssm==1.134.0",
        "aws-cdk.aws-s3==1.134.0",
        "aws-cdk.aws-efs==1.134.0",
        "aws-cdk.aws-msk==1.134.0",
        "prometheus-api-client",
        "pyyaml"
    ],

    python_requires=">=3.6",

    classifiers=[
        "Development Status :: 4 - Beta",

        "Intended Audience :: Developers",

        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",

        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",

        "Typing :: Typed",
    ],
)
