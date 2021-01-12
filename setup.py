from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='ds-repltest',
    version='1.1',
    description='LDAP Replication Check for 389ds',
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="389ds rhds directory LDAP check monitor replication",
    packages=['dsReplTest'],
    scripts=['ds-repltest.py'],
    include_package_data = False,
    package_data={
        'dsReplTest': ['etc/ds-repltest.conf.dist',
                       'common.py', 'ldap.py',
                       'static/*', 'templates/*' ],
    },
    data_files=[
        ('/etc/ds-repltest', ['dsReplTest/etc/ds-repltest.conf.dist']),
        ('/usr/share/doc/ds-repltest', ['README.md']),
        ('/usr/share/licenses/ds-repltest', ['LICENSE']),
        ('/usr/lib/systemd/system', ['dsReplTest/systemd/ds-repltest.service']),
        ('/etc/logrotate.d', ['dsReplTest/systemd/ds-repltest.logrotate'])
    ],
    install_requires=[
        'PyYAML>=5.2',
        'systemd-python>=234',
        'Flask>=0.10.1',
        'python-ldap>=3.1.0',
        'waitress>=0.8.9'
    ],
    python_requires='>=3.6',
    url='https://github.com/falon/ds-repltest',
    license='Apache License 2.0',
    author='Marco Favero',
    author_email='m.faverof@gmail.com',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 4 - Beta",
        "Environment :: No Input/Output (Daemon)",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.8",
        "Environment :: Web Environment",
        "Framework :: Flask",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Systems Administration :: Authentication/Directory :: LDAP",
        "Topic :: Utilities"
    ]
)
