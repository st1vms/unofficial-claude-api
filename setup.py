from setuptools import setup, find_packages

with open("requirements.txt", "r") as fp:
    install_requires = fp.read().splitlines()

__DESCRIPTION = """Unofficial Claude2 API supporting direct HTTP chat creation/deletion/retrieval, \
message attachments and auto session gathering using Firefox with geckodriver. \
"""

with open("README.md", "r") as fp:
    __LONG_DESCRIPTION = fp.read().lstrip().rstrip()

setup(
    name="unofficial-claude2-api",
    version="0.1.0",
    author="st1vms",
    author_email="stefano.maria.salvatore@gmail.com",
    description=__DESCRIPTION,
    long_description=__LONG_DESCRIPTION,
    url="https://github.com/st1vms/unofficial-claude2-api",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=install_requires,
)
