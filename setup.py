from setuptools import find_packages, setup

setup(
    name="pyftpdrive",
    version="0.1.0",
    description="Mount FTP server as a local Windows drive",
    author="Daniel T Sasser II",
    packages=find_packages(),
    install_requires=[
        "winfspy>=0.8.0",
        "cachetools>=5.0.0",
    ],
    entry_points={
        "console_scripts": [
            "pyftpdrive=pyftpdrive.__main__:main",
        ],
    },
    python_requires=">=3.10",
    extras_require={
        "dev": [
            "pytest",
            "pyftpdlib",
            "build",
            "twine",
        ],
    },
)
