'''
by: Arash Molavi Kakhki (arash@ccs.neu.edu)


Notes:
    Initially I used an extension I wrote to clear cache:
        configs.set('extPath', os.path.abspath('extension_cache_remover'))
        commonOptions = ['--load-extension={}'.format(configs.get('extPath'))]
    
    But now I use Chrome's benchmarking to clear cache:
        commonOptions += ['--enable-benchmarking', '--enable-net-benchmarking']
        driver.execute_script("return chrome.benchmarking.clearCache();")
        driver.execute_script("return chrome.benchmarking.clearHostResolverCache();")
        driver.execute_script("return chrome.benchmarking.clearPredictorCache();")
        driver.execute_script("return chrome.benchmarking.closeConnections();")
        
    This can close connections and clear DNS cache too. So basically closing browsers between runs is not necessary anymore (I have left the functionality there in case for later)
        
    

Example:
    python engineChrome.py --platform=mac     --networkInt=en0  --rounds=3 --runQUICserver=False --runTcpProbe=False --against=GAE --doIperf=False --xvfb=False --testPage=index_100KBx10.html --quic-version=30 --testDir=testKir --closeDrivers=False --clearCacheConns=False
    python engineChrome.py --platform=mac     --networkInt=en5  --rounds=3 --runQUICserver=True  --runTcpProbe=False --against=GCP --doIperf=False --xvfb=False --testPage=index_100KBx10.html --quic-version=30 --testDir=testKir --closeDrivers=False --clearCacheConns=False --quic_server_path=quic_server-51.0.2704.106-21afa7f9b196ebd977e7215aa48ecb0effd1f8c3
    
    python engineChrome.py --platform=linux64 --networkInt=eth0 --rounds=3 --runQUICserver=False --runTcpProbe=False --against=GAE --doIperf=False --xvfb=False --testPage=index_100KBx10.html --quic-version=30 --closeDrivers=False --testDir=sel-noClear  --clearCacheConns=False
    python engineChrome.py --platform=linux64 --networkInt=eth0 --rounds=3 --runQUICserver=False --runTcpProbe=False --against=GAE --doIperf=False --xvfb=False --testPage=index_100KBx10.html --quic-version=30 --closeDrivers=False --testDir=sel-yesClear --clearCacheConns=True

    
    python engineChrome.py --platform=linux64 --networkInt=eth0 --rounds=3 --runQUICserver=False --runTcpProbe=False --against=EC2 --doIperf=False --xvfb=False --testPage=index_5KBx1.html --quic-version=30 --closeDrivers=False --clearCacheConns=True --testDir=proxyTest --cases=quic-proxy
'''

try:
    from selenium import webdriver
except ImportError:
    print '\n####################################################################'
    print 'SELENIUM NOT AVAILABLE!!! You can only run tests using HAR capturer!!!'
    print '####################################################################\n'
import sys, os, time, pickle, socket, json, subprocess, traceback, multiprocessing, commands
import stats
import sideTrafficGenerator
from pythonLib import *
from functools import wraps
import errno
import os
import signal

class TimeoutError(Exception):
    pass

def timeout(seconds=10, error_message=os.strerror(errno.ETIME)):
    def decorator(func):
        def _handle_timeout(signum, frame):
            raise TimeoutError(error_message)

        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result

        return wraps(func)(wrapper)

    return decorator

class ModifyEtcHosts(object):
    def __init__(self):
        self.hosts = set()
        
    def remove(self, hosts):
        hosts = [h for h in hosts if h not in ['localhost', '127.0.0.1']]
        
        with open('/etc/hosts', 'r') as f:
            hostsLines = f.readlines()
        
        newL = []
        for l in hostsLines:
            l2 = l.strip().split()
            if l2:
                h  = l2[-1]
                ip = l2[0]
                if h in hosts:
                    self.hosts.discard(ip)
                    continue
                newL.append(l)
            
        toWrite = ''.join(newL)
    
        with open('hosts', 'w') as f:
            f.write(toWrite)
        
        os.system('sudo cp hosts /etc/hosts')
        
    def add(self, hosts, hostIP=None):
        
        hosts = [h for h in hosts if h not in ['localhost', '127.0.0.1']]
        
        self.remove(hosts)
        
        toAppend = []
        
        for h in hosts:
            if Configs().get('serverIsLocal'):
                ip = '127.0.0.1'
            else:
                if hostIP:
                    ip = hostIP
                else:
                    ip = socket.gethostbyname(h)
            toAppend.append('{}\t{}\n'.format(ip, h))
            self.hosts.add(ip)
            
        os.system('cp /etc/hosts hosts')
        
        with open('hosts', 'a') as f:
            for a in toAppend:
                f.write(a)
            
        os.system('sudo cp hosts /etc/hosts')
        
    def show(self):
        os.system('cat /etc/hosts')

class Ping(object):
    def __init__(self):
        self.p = None
    
    def _ping(self, host, output):
        os.system('ping {} > {}'.format(host, output))
        
    def start(self, host, output):
        self.p  = multiprocessing.Process(target=self._ping, args=(host, output,))
        self.p.start()
        
    def stop(self):
        self.p.terminate()

class TCPDUMP(object):
    def start(self, outFile, interface=None, ports=None, hosts=None):
        self.command = ['sudo', 'tcpdump', '-w', outFile]
        
        if interface:
            self.command += ['-i', interface]
        
        if ports:
            self.command += ['port', ports.pop()]
            while ports:
                self.command += ['or', 'port', ports.pop()]

            if hosts:
                self.command += ['and']
        
        if hosts:
            self.command += ['host', hosts.pop()]
            while hosts:
                self.command += ['or', 'host', hosts.pop()]
        
        self.p  = subprocess.Popen(self.command)
        
        PRINT_ACTION('Sleeping 3 seconds so tcpdump starts', 0)
        time.sleep(3)
        
        self.command = ' '.join(self.command)
        
        return self.command
    
    def stop(self):
        '''
        I cannot use subprocess kill because the process has started with sudo
        Unless I change groups and users and stuff, I do need to run tcpdump
        with sudo.
        '''
        
        os.system('sudo pkill -f "{}"'.format(self.command))
        time.sleep(3)

def getBrowserMajor(browserPath, platform):
    if platform == 'mac':
        cmd = '{} --version'.format(browserPath.replace(' ', '\\ '))
        version = commands.getoutput(cmd)
        return int(version.strip().split(' ')[-1].split('.')[0])
    elif platform == 'linux64':
        cmd = '{} --product-version'.format(browserPath)
        
        print cmd
        version = commands.getoutput(cmd)
        return int(version.split('.')[0])

def selectChromeDriverPath(browserPath, platform):
    '''
    According to below link, every chromedriver version only supports a number of chrome versions. This is
    apparantly due to the fact that the debugging protocol keeps changing and it's not always compatible.
    This function selects the appropriate version of chromedriver based on the chrome version being used.
    
    See: http://chromedriver.storage.googleapis.com/2.22/notes.txt
    '''
    if not browserPath:
        return os.path.abspath('chromeDrivers/{}/chromedriver_2.22'.format(platform))
    else:
        major = getBrowserMajor(browserPath, platform)
        if   major >= 60:
            return os.path.abspath('chromeDrivers/{}/chromedriver_2.31'.format(platform))
        if   major >= 49:
            return os.path.abspath('chromeDrivers/{}/chromedriver_2.22'.format(platform))
        elif major >= 46:
            return os.path.abspath('chromeDrivers/{}/chromedriver_2.21'.format(platform))
        elif major >= 43:
            return os.path.abspath('chromeDrivers/{}/chromedriver_2.20'.format(platform))

def commandSimpleServer_runQuicServer_runTcpProbe(what, logName=None, host="localhost", tcpprobePort='443', port=55555, quic_server_path=''):
    sock   = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    toSend = what + ';' + logName.strip() + ';' + str(time.time())
    
    if what == 'start_quicServer' and quic_server_path:
        toSend += ';' + quic_server_path
    elif what == 'start_tcpprobe':
        toSend += ';' + str(tcpprobePort)
    
    try:
        sock.connect((host, port))
        sock.sendall(toSend)
    
    except Exception as e:
        print '\n\nFailed to command the remote host! (command: {}) Exiting... \n {}\n\n'.format(what, e)
        return -13
    
    received = sock.recv(1024)
    
    sock.close()
    
    time.sleep(5)   #wait a bit so the server runs
    
    return received
    
class Driver(object):
    def __init__(self, chromeDriverPath, browserPath, options, pageLoadTimeOut=None):
        self.chromeDriverPath = chromeDriverPath
        self.browserPath      = browserPath
        self.options          = options
        self.pageLoadTimeOut  = pageLoadTimeOut
        self.driver           = None
    
    @timeout(20)
    def open(self):
        webdriver.ChromeOptions.binary_location = self.browserPath
        
        self.driver = webdriver.Chrome(executable_path=self.chromeDriverPath, chrome_options=self.options)
        
        if self.pageLoadTimeOut:
            self.driver.set_page_load_timeout(self.pageLoadTimeOut)
        
    @timeout(20)
    def close(self):
        self.driver.close()
        self.driver.quit()
        
    def get(self, url):
        self.driver.get(url)
        
    def sizePosition(self, case=None, size=(700, 400)):
        if not case:
            pos  = (0  , 0)
        elif case == 'quic':
            pos  = (0  , 0)
        elif case == 'https':
            pos  = (250  , 350)
        elif case == 'http':
            pos  = (0  , 900)
        elif case == 'quic-proxy':
            pos  = (0  , 900)
        elif case == 'https-proxy':
            pos  = (0  , 900)
            
        self.driver.set_window_size(size[0], size[1])
        self.driver.set_window_position(pos[0], pos[1])
    
    def clearCacheAndConnections(self):
        self.driver.execute_script("return chrome.benchmarking.clearCache();")
        self.driver.execute_script("return chrome.benchmarking.clearHostResolverCache();")
        self.driver.execute_script("return chrome.benchmarking.clearPredictorCache();")
        self.driver.execute_script("return chrome.benchmarking.closeConnections();")

def beforeExit(tcpdumpObj=None, drivers=None, modifyEtcHosts=None, logName=False, tcpprobePid=False):
    
    configs = Configs()
    
    #Killing TCPDUMP
    if tcpdumpObj:
        PRINT_ACTION('Killing TCPDUMP', 0)
        if configs.get('tcpdump'):
            tcpdumpObj.stop()
     
    #Asking remote host to stop QUIC server
    if logName:
        if configs.get('runQUICserver'):
            PRINT_ACTION('Asking remote host to stop QUIC server', 0)
            r = commandSimpleServer_runQuicServer_runTcpProbe('stop_quicServer', logName=logName, host=configs.get('host')['quic'])
            PRINT_ACTION('Done: '+str(r), 2, action=False)
    
    #Asking remote host to stop tcpProbe
    if tcpprobePid:
        if configs.get('runQUICserver'):
            PRINT_ACTION('Asking remote host to stop tcpprobe', 0)
            r = commandSimpleServer_runQuicServer_runTcpProbe('stop_tcpprobe' , logName=tcpprobePid, host=configs.get('host')['https'])
            PRINT_ACTION('Done: '+str(r), 2, action=False)
    
    #Reverting modifications to /etc/hosts
    if modifyEtcHosts:
        PRINT_ACTION('Reverting modifications to /etc/hosts', 0)
        modifyEtcHosts.remove( [ configs.get('host')['quic'], configs.get('host')['http'], configs.get('host')['https'] ] )
    
    if configs.get('doSideTraffic'):
        trafficGenerator.stopSending()

    #Closing drivers
    if drivers:
        PRINT_ACTION('Closing drivers', 0)
        for case in drivers:
            try:
                drivers[case].close()
            except TimeoutError:
                print 'Got stuck closing drivers! :-s'
    
    time.sleep(3)

def initialize():
    configs = Configs()
    
    configs.set('waitBetweenLoads'  , 1)
    configs.set('waitBetweenRounds' , 1)
    configs.set('rounds'            , 10)
    configs.set('pageLoadTimeout'   , 120)
    configs.set('tcpdump'           , True)
    configs.set('serverIsLocal'     , False)
    configs.set('runQUICserver'     , True)
    configs.set('runTcpProbe'       , False)
    configs.set('doSideTraffic'     , False)
    configs.set('closeDrivers'      , False)
    configs.set('clearCacheConns'   , True)
    configs.set('separateTCPDUMPs'  , False)
    configs.set('doStats'           , False)
    configs.set('browserPath'       , False)
    configs.set('doSecondDL'        , False)    #On a phone, we need to close browser for back-to-back runs which prevents 0-RTT for QUIC. If this is True, for QUIC downloads, it does 2, and save the result (HAR) for the second one which has 0-RTT
    configs.set('backgroundPings'   , False)
    configs.set('quicServerIP'      , None)
    configs.set('httpServerIP'      , None)
    configs.set('httpsServerIP'     , None)
    configs.set('modifyEtcHosts'    , True)
    configs.set('quicProxyIP'       , '[URL of server running QUIC proxy]')
    configs.set('httpsProxyIP'      , '[URL of server running HTTP proxy]')
    configs.set('cases'             , 'http,https,quic')
    configs.set('quicProxyPort'     , '443')
    configs.set('httpsProxyPort'    , '443')
    configs.set('platform'          , 'linux64')
    configs.set('against'           , 'GCP')        #Possible inputs are: GCP (Google Cloud Platform), GAE (Google App Engine), or EC2 (Amazon)
    configs.set('quic_server_path'  , '')
    configs.set('mainDir'           , os.path.abspath('../data') + '/results')
    configs.set('extPath'           , os.path.abspath('extension_cache_remover'))
    
    configs.read_args(sys.argv)
    
    '''
    Important: the following MUST be done AFTER read_args in case "--against" gets overridden 
    '''
    if configs.get('against') == '[your server name]':
        configs.set('host', {'quic'         :'[URL of host running QUIC server]',
                             'http'         :'[URL of host running HTTP server]',
                             'https'        :'[URL of host running HTTPS server]',
                             'https-proxy'  :'[URL of host running HTTP proxy server]',
                             'quic-proxy'   :'[URL of host running QUIC proxy server]',})
        
        
    configs.check_for(['testDir', 'testPage', 'networkInt'])
    
    if configs.get('testDir').endswith('/'):
        configs.set( 'testDir', configs.get('testDir')[:-1] )
    
    configs.set('chromedriver', selectChromeDriverPath(configs.get('browserPath'), configs.get('platform')))
    
    configs.set('testDir', configs.get('mainDir') + '/' + configs.get('testDir') )
    
    if os.path.isdir(configs.get('testDir')):
        print 'Test directory already exists! Use another name!'
        sys.exit()
    
    #Creating the necessary directory hierarchy
    PRINT_ACTION('Creating the necessary directory hierarchy', 0)        
    testDir         = configs.get('testDir')
    resultsDir      = '{}/resultsDir'.format(testDir)
    statsDir        = '{}/statsDir'.format(testDir)
    userDirs        = '{}/userDirs'.format(testDir)
    screenshotsDir  = '{}/screenshots'.format(testDir)
    dataPaths       = '{}/dataPaths'.format(testDir)
    netLogs         = '{}/netLogs'.format(testDir)
    tcpdumpDir      = '{}/tcpdumps'.format(testDir)
    tcpdumpFile     = '{}/{}_tcpdump.pcap'.format(testDir, os.path.basename(testDir))
    configsFile     = '{}/{}_configs.txt'.format(testDir, os.path.basename(testDir))
      
    os.system('mkdir -p {}'.format(resultsDir))
    os.system('mkdir -p {}'.format(statsDir))
    os.system('mkdir -p {}'.format(userDirs))
    os.system('mkdir -p {}'.format(screenshotsDir))
    os.system('mkdir -p {}'.format(dataPaths))
    os.system('mkdir -p {}'.format(netLogs))
    os.system('mkdir -p {}'.format(tcpdumpDir))
     
    #Write configs to file (just for later reference)
    configs.write2file(configsFile)
    
    cases         = configs.get('cases').split(',')
    methods       = {'quic'         :'https', 
                     'http'         :'http', 
                     'https'        :'https',
                     'https-proxy'  :'https', 
                     'quic-proxy'   :'https'}
    
    
    uniqeOptions  = {'quic' : [
                             '--enable-quic',
                             '--origin-to-force-quic-on={}:443'.format(configs.get('host')['quic']),
                             '--quic-host-whitelist={}'.format(configs.get('host')['quic']),
                             ],
                    
                    'quic-proxy' : [
                             '--enable-quic',
                             '--origin-to-force-quic-on={}:443'.format(configs.get('host')['quic']),
                             '--quic-host-whitelist={}'.format(configs.get('host')['quic']),
                             '--host-resolver-rules=MAP {}:443 {}:{}'.format(configs.get('host')['quic'], configs.get('quicProxyIP'), configs.get('quicProxyPort')),
                             ],
                     
                    #Because I have to use "echo" and "adb shell" to write to a file when setting flags for Chrome on Android,
                    #I need quotations and escapes and stuff. SO the "host-resolver-rule" option's quoatation for mobile is different
                    #In engineAndroid_harCapturer.py, we do uniqeOptions['quic-proxy'] = uniqeOptions['quic-proxy-mobile'] 
                    'quic-proxy-mobile' : [
                             '--enable-quic',
                             '--origin-to-force-quic-on={}:443'.format(configs.get('host')['quic']),
                             '--quic-host-whitelist={}'.format(configs.get('host')['quic']),
                             "--host-resolver-rules=\"MAP {}:443 {}:{}\"".format(configs.get('host')['quic'], configs.get('quicProxyIP'), configs.get('quicProxyPort')),
                             ],
                     
                    'http' : [
                             '--disable-quic',
                             ],
                    
                    'https': [
                             '--disable-quic',
                             ],
                    'https-proxy': [
                             '--disable-quic',
                             '--host-resolver-rules=MAP {}:443 {}:{}'.format(configs.get('host')['https'], configs.get('httpsProxyIP'), configs.get('httpsProxyPort')),
                             ],               
                    }
    
    try:
        configs.get('quic-version')
        uniqeOptions['quic'].append( '--quic-version=QUIC_VERSION_{}'.format(configs.get('quic-version')) )
        uniqeOptions['quic-proxy'].append( '--quic-version=QUIC_VERSION_{}'.format(configs.get('quic-version')) )
        uniqeOptions['quic-proxy-mobile'].append( '--quic-version=QUIC_VERSION_{}'.format(configs.get('quic-version')) )
    except KeyError:
        pass
    
    
    dIPs = {'quic'          : configs.get('quicServerIP'),
            'http'          : configs.get('httpServerIP'),
            'https'         : configs.get('httpsServerIP'),
            'https-proxy'   : configs.get('httpsProxyIP'),
            'quic-proxy'    : configs.get('quicProxyIP')
            }
    
    modifyEtcHosts = ModifyEtcHosts()
    if configs.get('modifyEtcHosts'):
        for case in cases:
            try:
                modifyEtcHosts.add([configs.get('host')[case]])
            except:
                print '\t\tmodifyEtcHosts did not add host for:', case
                pass
            if case == 'quic-proxy':
                modifyEtcHosts.add([configs.get('quicProxyIP')])
            if case == 'https-proxy':
                modifyEtcHosts.add([configs.get('httpsProxyIP')])
    
    return configs, cases, methods, testDir, resultsDir, statsDir, userDirs, screenshotsDir, dataPaths, netLogs, tcpdumpDir, tcpdumpFile, uniqeOptions, modifyEtcHosts

def main():
    #The following line is to make sure the script has sudo privilage to run tcpdump
    os.system('sudo echo')


    #Setting up configs
    PRINT_ACTION('Reading configs file and args', 0)
    configs, cases, methods, testDir, resultsDir, statsDir, userDirs, screenshotsDir, dataPaths, netLogs, tcpdumpDir, tcpdumpFile, uniqeOptions, modifyEtcHosts = initialize()
    configs.show_all()
    
    
    #Creating options
    '''
    IMPORTANT: --enable-benchmarking --enable-net-benchmarking: to enable the Javascript interface that allows chrome-har-capturer to flush the DNS cache and the socket pool before loading each URL.
               in other words, clear cache and close connections between runs! 
    '''
    PRINT_ACTION('Creating options', 0)
    drivers       = {}    
    stat          = stats.Stats(netInt=configs.get('networkInt'))
    chromeOptions = {}
    commonOptions = ['--no-first-run']
    
    if configs.get('clearCacheConns'):
        commonOptions += ['--enable-benchmarking', '--enable-net-benchmarking']

    
    #Creating driver instances and modifying /etc/hosts
    PRINT_ACTION('Creating driver options and modifying /etc/hosts', 0)
    for case in cases:
        #Modify /etc/hosts
#         modifyEtcHosts.add([configs.get('host')[case]], hostIP=configs.get('serverIP'))
#         
#         if case.endswith('proxy'):
#             modifyEtcHosts.add([configs.get('quicProxyIP')])
        
        chromeOptions[case] = webdriver.ChromeOptions()
        unCommonOptions     = ['--user-data-dir={}/{}'.format(userDirs, case),
                               '--data-path={}/{}'.format(dataPaths, case),
#                                '--log-net-log={}/{}.json'.format(netLogs, case),
                               ]
         
        for option in uniqeOptions[case] + commonOptions + unCommonOptions:
            chromeOptions[case].add_argument(option)
        
        drivers[case] = Driver(configs.get('chromedriver'), configs.get('browserPath'), chromeOptions[case], pageLoadTimeOut=configs.get('pageLoadTimeout'))
        
        if not configs.get('closeDrivers'):
            print '\tFor: {}...\t'.format(case),; sys.stdout.flush()
            try:
                drivers[case].open()
            except TimeoutError:
                print 'Got stuck opening driver! Drivers are persistant, so cannot continue. Exiting! :-s'
                sys.exit()
            print 'Done'
            
            drivers[case].sizePosition(case=case)
    
    #Starting TCPDUMP
    if configs.get('tcpdump'):
        if configs.get('separateTCPDUMPs'):
            tcpdumpObj = None
        else:
            PRINT_ACTION('Starting TCPDUMP', 0)
            tcpdumpObj = TCPDUMP()
            tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'], hosts=modifyEtcHosts.hosts)
    
    
    #Asking remote host to start QUIC server
    logName     = False
    tcpprobePid = False
    if not configs.get('against') == 'GAE':
        if configs.get('runQUICserver') and 'quic' in cases:
            PRINT_ACTION('Asking remote host to start QUIC server', 0)
            logName  = '_'.join(['quic_server_log', testDir.rpartition('/')[2], configs.get('testPage')]) + '.log'
            
            exitCode = commandSimpleServer_runQuicServer_runTcpProbe('start_quicServer', logName=logName, host=configs.get('host')['quic'], quic_server_path=configs.get('quic_server_path'))
            
            PRINT_ACTION('Done: ' + str(exitCode), 2, action=False)
            if exitCode == -13:
                beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=modifyEtcHosts, logName=logName)
                sys.exit()
        
        
        #Asking remote host to start runTcpProbe
        if configs.get('runTcpProbe'):
            PRINT_ACTION('Asking remote host to start tcpprobe', 0)
            logNameTCP  = '_'.join(['tcpprobe_log', testDir.rpartition('/')[2], configs.get('testPage')]) + '.log'
            tcpprobePid = commandSimpleServer_runQuicServer_runTcpProbe('start_tcpprobe', logName=logNameTCP, host=configs.get('host')['https'])
            PRINT_ACTION('Done: ' + str(tcpprobePid), 2, action=False)
            if tcpprobePid == -13:
                beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=modifyEtcHosts, logName=logName, tcpprobePid=tcpprobePid)
                sys.exit()
    
    
    #Generate side traffic
    if configs.get('doSideTraffic'):
        trafficGenerator = sideTrafficGenerator.TrafficGenerator( 'achtung.ccs.neu.edu' )
        trafficGenerator.startSending()
    
    #Firing off the tests
    PRINT_ACTION('Firing off the tests', 0)
    for round in range(1, configs.get('rounds')+1):
        
        
        for case in cases:
            testID = '{}_{}'.format(case, round)
            PRINT_ACTION('Doing: {}/{}'.format(testID, configs.get('rounds')), 1, action=False)            
            
            if case.startswith('quic') and (not (configs.get('against') == 'GAE')):
                url = '{}://{}/{}'.format(methods[case], configs.get('host')[case], configs.get('testPage'), testID)
            else:
                url = '{}://{}/?page={}&testID={}'.format(methods[case], configs.get('host')[case], configs.get('testPage'), testID)
            
            if configs.get('doStats'):
                stat.start()

            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpFile = '{}/{}_{}_tcpdump.pcap'.format(tcpdumpDir, os.path.basename(testDir), testID)
                tcpdumpObj  = TCPDUMP()
                tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'], hosts=modifyEtcHosts.hosts)


            if configs.get('closeDrivers'):
                PRINT_ACTION('Opening driver: '+ testID, 2, action=False)
                try:
                    drivers[case].open()
                except TimeoutError:
                    print 'Got stuck opening driver! :-s'
                    continue
                drivers[case].sizePosition(case=case)
                
            try:
                drivers[case].get(url)
            except Exception as e:
                print '###### EXCEPTION during {}#######'.format(testID)
                print e
                traceback.print_exc()
                continue
            
            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpObj.stop()
             
            windowPerformance = drivers[case].driver.execute_script("return window.performance.getEntriesByType('resource');")\
            
            try:
                print windowPerformance[0]['duration']
            except:
                pass
            
            print windowPerformance
             
            with open(resultsDir + '/' + testID + '.json', "w") as f:
                json.dump( {'PerformanceResourceTiming' : windowPerformance, 'testID' : testID}, f )

            if configs.get('doStats'):
                statsRes = stat.stop()
                stat.save(statsDir+'/'+testID+'.json')
            
            drivers[case].driver.save_screenshot('{}/{}.png'.format(screenshotsDir, testID))
            
            if configs.get('clearCacheConns'):
                drivers[case].clearCacheAndConnections()
            
            if configs.get('closeDrivers'):
                try:
                    drivers[case].close()
                except TimeoutError:
                    print 'Got stuck closing driver! :-s'
            
            time.sleep(configs.get('waitBetweenLoads'))

        if round != configs.get('rounds'):
            PRINT_ACTION('Sleeping between rounds: {} seconds ...'.format(configs.get('waitBetweenRounds')), 0)
            time.sleep(configs.get('waitBetweenRounds'))
        
#         raw_input('berim ?')
    
    PRINT_ACTION('Running final beforeExit ...', 0)
    if configs.get('closeDrivers'):
        drivers=None
    if configs.get('separateTCPDUMPs'):
        tcpdumpObj=None
    beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=modifyEtcHosts, logName=logName, tcpprobePid=tcpprobePid)
    
if __name__=="__main__":
    main()