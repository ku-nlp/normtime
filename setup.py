from setuptools import setup, find_packages

setup(
    name="normtime",
    version="0.0.1",
    packages=find_packages(),
    data_files=[("rule", ["./rule/gengo.json", "./rule/strRule.json"])]
)
