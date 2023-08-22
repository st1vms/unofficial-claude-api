from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().splitlines()

__DESCRIPTION = """Unofficial Claude2 API supporting direct HTTP chat creation/deletion/retrieval, \
message attachments and auto session gathering using Firefox with geckodriver. \
"""

setup(
    name="unofficial-claude2-api",
    version="0.1.0",
    author="st1vms",
    description=__DESCRIPTION,
    packages=find_packages(),
    install_requires=install_requires,
)
