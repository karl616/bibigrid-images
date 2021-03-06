#!/usr/bin/env python
from subprocess import check_output, CalledProcessError, STDOUT
from datetime import datetime
from os import geteuid, remove, chmod, environ
from argparse import ArgumentParser, SUPPRESS
from pkgutil import get_data
from sys import argv
from cfg import *

VERSION=0.1
HTTP_PROXY=environ.get('HTTP_PROXY')
HTTPS_PROXY=environ.get('HTTPS_PROXY')
KEYSERVER_OPTIONS=""
if (HTTP_PROXY != None):
    print "using proxy setting from environment"
    KEYSERVER_OPTIONS="--keyserver-options "+HTTP_PROXY


DEFAULT_USERNAME='ubuntu'
DEFAULT_FILE_MODE=0644
IMAGE_TYPES=['master','slave']
APT_SLAVE_LIST='apt-slave.txt'
APT_MASTER_LIST='apt-master.txt'
APT_UPDATE_CMD='apt-get update'
GANGLIA_CONFIG='conf_default.php'
APT_SOURCES="echo 'deb http://us.archive.ubuntu.com/ubuntu trusty main universe' | sudo tee -a /etc/apt/sources.list;\n"+\
	"echo 'deb http://repos.mesosphere.io/ubuntu trusty main' | sudo tee /etc/apt/sources.list.d/mesosphere.list;\n"+\
	"echo 'deb https://apt.dockerproject.org/repo ubuntu-trusty main' | sudo tee -a /etc/apt/sources.list.d/docker.list;\n"+\
	"add-apt-repository -y ppa:openjdk-r/ppa;\n"+\
	"add-apt-repository -y ppa:gluster/glusterfs-3.5"
APT_KEYS='apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 '+KEYSERVER_OPTIONS+' --recv-keys 58118E89F3A912897C070ADBF76221572C52609D;\n'+\
	'apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 '+KEYSERVER_OPTIONS+' --recv E56151BF;\n'

APT_INSTALL_CMD='DEBIAN_FRONTEND=noninteractive apt-get -y --force-yes -qq -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install {0}'
HADOOP_URL='https://bibiserv.cebitec.uni-bielefeld.de/resources/bibigrid/software/hadoop-2.7.3.tar.gz'
SPARK_URL='https://bibiserv.cebitec.uni-bielefeld.de/resources/bibigrid/software/spark-2.1.1-bin-hadoop2.7.tgz'
CASSANDRA_URL='https://bibiserv.cebitec.uni-bielefeld.de/resources/bibigrid/software/apache-cassandra-3.10-bin.tar.gz'
try:
    V=get_data('__main__','VERSION')
except:
    V='unknown version'

def createImage():
    #parse command-line arguments
    parser = ArgumentParser(description='Create a BiBiGrid Master/Slave Image. Use proxy properties from environment')
    parser.add_argument('--version', action='version', version=V)
    parser.add_argument('--for', dest='imageType', required=True, choices=IMAGE_TYPES, help='The type of the image to be created.')
    parser.add_argument('--username', dest='username', default=DEFAULT_USERNAME, help='The username of the current user (default: ubuntu).')
    parser.add_argument('--skip-apt', dest='skipApt', action='store_true', help='Skip package installation entirely.')
    parser.add_argument('--step-by-step-apt', dest='stepByStepApt', action='store_true', help='Invoke apt separately for every package.')
    parser.add_argument('--en', dest='en', action='store_true', help='Enhanced Networking for C3,R3 and I2 instances.')
    args = parser.parse_args()
    master, slave = args.imageType == 'master', args.imageType == 'slave'
    username=args.username
    en = args.en

    #check if running as root
    if not geteuid() == 0:
        exit('Script must be run as root, e.g.: sudo {0} ...'.format(argv[0]))

    infoHeader()
    print
    print 'Creating image for: '+args.imageType

    step=1
    if master:
        steps=7
    else:
        steps=4


    step = nextStep(step,steps,'Tools and programs') #**************

    if args.skipApt:
        print 'apt skipped on user request.'
    else:
        aptUpdate()
        aptList = []
        if slave:
            aptList = get_data('__main__',APT_SLAVE_LIST).split('\n')
        elif master:
            aptList = get_data('__main__',APT_MASTER_LIST).split('\n')
        if args.stepByStepApt:
            for pkg in aptList:
                if pkg:
                    apt(pkg)
        else:
            print 'Installing all packages at once. Please be patient....'
            pkgString = " ".join(aptList)
            try:
                check_output(APT_INSTALL_CMD.format(pkgString), stderr=STDOUT, shell=True)
                installed = True
            except CalledProcessError as e:
                installed = False
            if installed:
                print '[All packages]: Installation successful.'
            else:
                print '[All packages]: Installation FAILED!'
                print 'Installation returned the following message:'
                print ' -------'
                for line in e.output.split('\n'):
                    print ' | '+line
                print ' -------'
                exit(11)
        print 'Upgrading system...'
        run('DEBIAN_FRONTEND=noninteractive apt-get -qq -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade')

    run('update-alternatives --set java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java')
    run('echo "export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64" >> /home/{0}/.bashrc'.format(username))
    run('echo "export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64" >> /home/{0}/.profile'.format(username))
    run('adduser ubuntu docker')    
    
    #****************** bibis3
    
    run ('curl https://bibiserv.cebitec.uni-bielefeld.de/resources/bibis3/bibis3.jar > /usr/local/bin/bibis3.jar')
    run ("echo echo -n '#!/bin/bash\njava -jar `dirname $0`/bibis3.jar $@\n' > /usr/local/bin/bibis3")
    run ("chmod 755 /usr/local/bin/bibis3") 
   
    #****************** swift
    run ('pip install python-swiftclient')
    
    #****************** hadoop
    run ("adduser --group hadoop")
    run ("adduser --system --home /opt/hadoop  --no-create-home --group hadoop")
    run ("adduser ubuntu hadoop")
   
    if master:
        run('wget {0} -O - | tar -C /opt -xzf - '.format(HADOOP_URL))
        run('mv /opt/hadoop-2.7.3 /opt/hadoop')
    if slave:
        run ("mkdir -p /opt/hadoop")
        
    run ("chown -R hadoop:hadoop /opt/hadoop")
    run ("chmod -R 775 /opt/hadoop")
    
    #******************* spark
    run ("adduser --group spark")
    run ("adduser ubuntu spark")
    
    if master:
        run('wget {0} -O - | tar -C /opt -xzf - '.format(SPARK_URL))
        run('mv /opt/spark-2.1.1-bin-hadoop2.7 /opt/spark')
    if slave:
        run('mkdir -p /opt/spark')
    run("chown -R ubuntu:spark /opt/spark")
    run("chmod -R 775 /opt/spark")
        
    #******************* cassandra
    run ("adduser --group cassandra")
    run ("adduser --system --home /opt/cassandra  --no-create-home --group cassandra")
    run ("adduser ubuntu cassandra")
    
    if master:
        run('wget {0} -O - | tar -C /opt --exclude=javadoc/* -xzf - '.format(CASSANDRA_URL))
        run('mv /opt/apache-cassandra-3.10 /opt/cassandra')
     
    if slave:
        run ("mkdir -p /opt/cassandra")
        
    run ("chown -R cassandra:cassandra /opt/cassandra")
    run ("chmod -R 775 /opt/cassandra")
    
    #****************** add all /opt/.*/bin into users path
    run("for p in $(find /opt -type d -regex '.*/bin'); do echo \"export PATH=\$PATH:$p\" >> /home/ubuntu/.bashrc; done")
    
    step = nextStep(step,steps,'Configuration files') #**************
    
    if master:
        configFile('/home/{0}/add_exec'.format(username), CFG_ADD_EXEC, 0755)
        configFile('/etc/hosts.allow', CFG_HOSTS_ALLOW)
        configFile('./hostgroup.conf', CFG_HOSTGROUP_CONF)
        configFile('./pe.conf', CFG_PE_CONF)
        configFile('./queue.conf', CFG_QUEUE_CONF)
        configFile('./global', CFG_SGE_CONF)
        configFile('./schedule.conf', CFG_SCHEDULE_CONF)
        run('service apache2 stop',False)
        run('service gmetad stop', False)
        run('service ganglia-monitor stop',False)
        configFile('/etc/ganglia/gmetad.conf', CFG_GMETAD_CONF)
        configFile('/etc/ganglia/gmond.conf', CFG_GMOND_CONF_MASTER)
        configFile('/etc/apache2/sites-available/ganglia.conf', CFG_APACHE_GANGLIA_CONF)
        configFile('/etc/apache2/conf-available/spark.conf',CFG_APACHE_SPARK_CONF)
	configFile('/etc/apache2/conf-available/hdfs.conf',CFG_APACHE_HDFS_CONF)
	configFile('/etc/apache2/conf-available/mesos.conf',CFG_APACHE_MESOS_CONF)
        configFile('/etc/apache2/conf-available/result.conf',CFG_APACHE_RESULT_CONF)
        configFile('/opt/cassandra/conf/cassandra.yaml', CFG_CASSANDRA)
        run('sed -i s/##NUM_TOKEN##/32/g /opt/cassandra/conf/cassandra.yaml',False)
        run("/usr/sbin/a2enmod proxy proxy_http proxy_html xml2enc rewrite",False)
       
        run("/usr/sbin/a2ensite ganglia",False)
    if slave:
        
        run('service ganglia-monitor stop',False)
        configFile('/etc/ganglia/gmond.conf', CFG_GMOND_CONF_SLAVE)
    
    #avoid starting zookepper, mesos-*, gridengine-* when booting instance  
    run('echo "manual" >> /etc/init/mesos-master.conf');
    run('echo "manual" >> /etc/init/mesos-slave.conf');
    run('echo "manual" >> /etc/init/zookeeper.conf');
        
    configFile('/etc/default/locale', CFG_DEFAULT_LOCALE)
    configFile('/home/{0}/.cloud-locale-test.skip'.format(username), '')
    
    # add userdata skript
    configFile('/etc/init.d/userdata', CFG_USERDATA, 0755)
    
    
    if en:
        print 'Enabling enhanced networking'
        configFile('/home/{0}/en.sh'.format(username), SCRIPT_EN)
        run('sh /home/{0}/en.sh'.format(username),False)
        delFile('/home/{0}/en.sh'.format(username))
	delFile('/home/{0}/ixgbevf-2.11.3.tar.gz'.format(username))
    if master:
        step = nextStep(step,steps,'GridEngine setup') #**************

        run('sudo -u sgeadmin qconf -am ubuntu', False)
        run('echo "export SGE_ROOT=/var/lib/gridengine" >> /home/{0}/.bashrc'.format(username))
        run('echo "export SGE_ROOT=/var/lib/gridengine" >> /home/{0}/.profile'.format(username))
        run('export SGE_ROOT=/var/lib/gridengine')
        run('qconf -au ubuntu users', False)
        run('qconf -Ahgrp ./hostgroup.conf', False)
        run('qconf -Ap ./pe.conf', False)
        run('qconf -Aq ./queue.conf', False)
	run('qconf -Msconf ./schedule.conf', False)
	run('qconf -Mconf ./global', False)

 #

    if master:
        step = nextStep(step,steps,'Schedule-DRMAAc Perl Module Installation') #**************
        run('''cd /tmp
        wget http://search.cpan.org/CPAN/authors/id/T/TH/THARSCH/Schedule-DRMAAc-0.81.tar.gz
        tar -xzf Schedule-DRMAAc-0.81.tar.gz
        cd Schedule-DRMAAc-0.81/
        export SGE_ROOT=/var/lib/gridengine
        ln -s /usr/include/drmaa.h
        perl Makefile.PL
        make
        sudo make install
        ''')

    step = nextStep(step,steps,'Services') #**************

    #run('update-rc.d userdata defaults')
    if master:
        run('update-rc.d -f gridengine-exec remove')

    step = nextStep(step,steps,'Other / Clean-up') #**************

    run('LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 locale-gen en_US.UTF-8')
    run('LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 dpkg-reconfigure locales')

    run('mkdir -p /vol')

    #clear apt cache
    run('apt-get clean')

    if slave:
        run('service gridengine-exec stop', False)
    if master:
        run('chown -R ganglia:ganglia /var/lib/ganglia/rrds/')
        run('service apache2 restart')
        delFile('./hostgroup.conf')
        delFile('./pe.conf')
        delFile('./queue.conf')
	delFile('./schedule.conf')
        delFile('/home/{0}/instantbibi.zip'.format(username))
	delFile('/home/{0}/global'.format(username))
	delFile('/usr/share/ganglia-webfrontend/conf_default.php')
	configFile('/usr/share/ganglia-webfrontend/conf_default.php',get_data('__main__', GANGLIA_CONFIG))
    #disable bash history
    run('ln -sf /dev/null /root/.bash_history')
    run('ln -sf /dev/null /home/{0}/.bash_history'.format(username))
    run('echo -n > /var/log/lastlog')

    #SELF DESTRUCTION
    delFile('./{0}'.format(argv[0]))

    print ''
    print '*** DONE ***'

    exit(0)







    
def apt(name,verifyCmd=None,verifyExpected=None):
    install(name, APT_INSTALL_CMD.format(name), verifyCmd, verifyExpected)

def aptUpdate():
    print 'Adding/Updating apt sources... '
    try:
	print '... keys ...'
        check_output(APT_KEYS, stderr=STDOUT,shell=True)
	print '... sources ...'
	check_output(APT_SOURCES, stderr=STDOUT,shell=True)
	print '... update ...'
        check_output(APT_UPDATE_CMD, stderr=STDOUT, shell=True)
    except CalledProcessError as e:
        print 'Adding/Updating apt sources FAILED:'
        print ' -------'
        for line in e.output.split('\n'):
            print ' | '+line
        print ' -------'
        exit(10)

def install(name,installCmd,verifyCmd=None,verifyExpected=None):
    print 'Installing '+name+' ...'
    #install
    try:
        check_output(installCmd, stderr=STDOUT, shell=True)
        installed = True
    except CalledProcessError as e:
        installed = False
    if installed:
        print '['+name+']: Installation successful.'
    else:
        print '['+name+']: Installation FAILED!'
        print 'Installation returned the following message:'
        print ' -------'
        for line in e.output.split('\n'):
            print ' | '+line
        print ' -------'
        exit(11)

    #verify
    if verifyCmd:
        try:
            output = check_output(verifyCmd, stderr=STDOUT, shell=True)
            verified = output.lower().find(verifyExpected.lower()) != -1
        except CalledProcessError:
            verified = False
        if verified:
            print '['+name+']: Verification successful.'
        else:
            print '['+name+']: Verification FAILED!'
            exit(12)

def configFile(path, content, mode=DEFAULT_FILE_MODE):
    try:
        with open(path, 'w') as f:
            print 'Creating '+path
            f.write(content)
            f.write('\n')
        try:
            chmod(path,mode)
        except:
            print 'FAILED to set mode on '+path
    except IOError as e:
        print 'FAILED to create '+path+': '+str(e)

def run(cmd,exitOnError=True):
    print 'Running: {0}'.format(cmd)
    try:
        check_output(cmd, stderr=STDOUT, shell=True)
    except CalledProcessError as e:
        print 'FAILED:'
        print ' -------'
        for line in e.output.split('\n'):
            print ' | '+line
        print ' -------'
        if exitOnError:
            exit(13)

def delFile(path):
    try:
        print 'Deleting file: {0}'.format(path)
        remove(path)
    except OSError as e:
        print 'FAILED to delete file: {0}'.format(e.strerror)

def infoHeader():
    print ''
    print '=== BiBiGrid Image Creator v'+str(VERSION)+' =='
    print ''
    print 'Current date/time: '+datetime.now().strftime('%Y-%m-%d %H:%M')
    print ''
    try:
        print 'Hostname: '+check_output('hostname', stderr=STDOUT, shell=True)
    except:
        print 'ERROR: could not get hostname'
    try:
        with open('/etc/issue.net','r') as issue:
            print 'Distribution: '+issue.next()
    except:
        print 'ERROR: could not get distribution'
    try:
        print 'System info:'
        print check_output('uname -a', stderr=STDOUT, shell=True)
    except:
        print 'ERROR: could not get system info'
    try:
        print 'Root volume info:'
        print check_output('df -h | grep -E "(Dateisystem|Filesystem|/$)"', stderr=STDOUT, shell=True)
    except:
        print 'ERROR: could not get root volume info'
    print ''

def nextStep(step,steps,msg):
    print ''
    print ''
    print '*** Step {0} of {1}: {2}'.format(step,steps,msg)
    print ''
    return step + 1
