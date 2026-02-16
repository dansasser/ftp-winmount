from setuptools import find_packages, setup

setup(
    name="ftp-winmount",
    version="0.2.0",
    description="Mount FTP, SFTP, or Google Drive as a local Windows drive",
    author="Daniel T Sasser II",
    packages=find_packages(),
    install_requires=[
        "winfspy>=0.8.0",
        "cachetools>=5.0.0",
        "paramiko>=3.0.0",
        "google-api-python-client>=2.100.0",
        "google-auth>=2.20.0",
        "google-auth-oauthlib>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "ftp-winmount=ftp_winmount.__main__:main",
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
