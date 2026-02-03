from setuptools import setup, find_packages

setup(
    name="pyftpdrive",
    version="0.1.0",
    description="Mount FTP server as a local Windows drive",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        "winfspy; python_version < '3.12'",
        "cachetools",
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
            "pytest-cov",
            "pyftpdlib",
            "build",
            "twine",
            "psutil",
        ],
    },
)
