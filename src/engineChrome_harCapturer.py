'''
by: Arash Molavi Kakhki (arash@ccs.neu.edu)
        
Notes:
    chrome_har_capturer clears cache and closes connection if called Chrome has been opened with benchmarking switches: --enable-benchmarking --enable-net-benchmarking
    So no need to close browser between runs! (I have left the functionality there in case for later)
       
Example:
    python engineChrome_harCapturer.py --testDir=hc-noClear  --networkInt=en5 --against=GCP --testPage=index_10MBx1.html --rounds=3  --closeDrivers=False --clearCacheConns=True --browserPath="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --quic_server_path=chromium_52.0.2743.116/src/out/Release/quic_server --platform=mac --cases=quic
    
    python engineChrome_harCapturer.py --testDir=hc-noClear  --networkInt=en5 --against=GCP --testPage=index_10MBx1.html --rounds=3  --closeDrivers=False --clearCacheConns=False --browserPath=chrome --quic_server_path=chromium_52.0.2743.116/src/out/Release/quic_server --platform=mac
    
    python engineChrome_harCapturer.py --networkInt=eth0 --against=GAE --testPage=index_100KBx10.html --rounds=10 --closeDrivers=False --browserPath=False --clearCacheConns=False --testDir=hc-noClear-10
    python engineChrome_harCapturer.py --networkInt=eth0 --against=GAE --testPage=index_100KBx10.html --rounds=10 --closeDrivers=False --browserPath=False --clearCacheConns=True  --testDir=hc-yesClear-10  

    python engineChrome_harCapturer.py --platform=linux64 --networkInt=eth0 --rounds=3 --runQUICserver=False --runTcpProbe=False --against=EC2 --doIperf=False --xvfb=False --testPage=index_10MBx1.html --quic-version=30 --closeDrivers=False --clearCacheConns=True --testDir=proxyTest --cases=quic-proxy  --browserPath=/home/arash/Release-52.0.2743.116-feb0ea45a0164eef52aa2631dd95d7c85fa65faa/chrome
    
    python engineChrome_harCapturer.py --testDir=test-mac  --networkInt=en0 --against=EC2 --testPage=index_1MBx1.html --rounds=2  --closeDrivers=False --clearCacheConns=True --runQUICserver=False --browserPath="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --platform=mac --cases=quic,quic-proxy
    
'''

import sys, os, time, pickle, socket, json, subprocess, traceback, multiprocessing, commands, random, string
import stats
import sideTrafficGenerator
from pythonLib import *
from engineChrome import ModifyEtcHosts, TCPDUMP, commandSimpleServer_runQuicServer_runTcpProbe, initialize, beforeExit, timeout, TimeoutError, Ping

browserLoadTimeout = 3*60

class Driver(object):
    def __init__(self):
        self.process         = None
        self.pageLoadTimeout = str(Configs().get('pageLoadTimeout'))

    def open(self, browserPath, options, debugPort):
        self.randomID  = ''.join(random.choice(string.ascii_letters + string.digits) for x in range(10))
        self.debugPort = debugPort
        cmd            = [browserPath] + options + ['--remote-debugging-port={}'.format(self.debugPort), '--randomID={}'.format(self.randomID)]
        self.process   = subprocess.Popen(cmd)
        time.sleep(2)
        
    def close(self):
        '''
        This is a hack I came up with to close the browser. Everytime a browser window is opened, it's ran with a dummy "--randomID" switch.
        When closing, this function kills processes with this randomID in their name.
        '''
        os.system('sudo pkill -f {}'.format(self.randomID))
    
    @timeout(browserLoadTimeout)
    def get(self, url, outFile):
        cmd = ['chrome-har-capturer', '--force', '--give-up', self.pageLoadTimeout, '--port', self.debugPort, '-o', outFile, url]

        print ' '.join(cmd)
        self.process  = subprocess.Popen(cmd)
        self.process.communicate()

        try:
            with open(outFile, 'r') as f:
                j = json.load(f)
                print '\t\t', j['log']['pages'][0]['pageTimings']['onLoad']
        except:
            pass
    
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
#     commonOptions = ['--no-first-run']
    commonOptions = [
                        '--no-first-run'
                        '--disable-background-networking', 
                        '--disable-client-side-phishing-detection', 
                        '--disable-component-update', 
                        '--disable-default-apps', 
                        '--disable-hang-monitor', 
                        '--disable-popup-blocking', 
                        '--disable-prompt-on-repost', 
                        '--disable-sync', 
                        '--disable-web-resources', 
                        '--metrics-recording-only', 
                        '--password-store=basic', 
                        '--safebrowsing-disable-auto-update', 
                        '--use-mock-keychain', 
                        '--ignore-certificate-errors'
                    ] 
    
    if configs.get('clearCacheConns'):
        commonOptions += ['--enable-benchmarking', '--enable-net-benchmarking']
    
    debugPorts = {
                  'http'        : '9220', 
                  'https'       : '9221',
                  'quic'        : '9222',
                  'quic-proxy'  : '9223',
                  'https-proxy' : '9224',
                  }
        
    #Creating driver instances and modifying /etc/hosts
    PRINT_ACTION('Creating driver options and modifying /etc/hosts', 0)
    for case in cases:
        #Modify /etc/hosts
#         modifyEtcHosts.add([configs.get('host')[case]], hostIP=configs.get('serverIP'))
#         
#         if case.endswith('proxy'):
#             modifyEtcHosts.add([configs.get('quicProxyIP')])
        
        drivers[case] = Driver()
        
        chromeOptions[case] = []
        unCommonOptions     = ['--user-data-dir={}/{}'.format(userDirs, case),
                               '--data-path={}/{}'.format(dataPaths, case),
#                                '--log-net-log={}/{}.json'.format(netLogs, case),
                               ]
         
        chromeOptions[case] = uniqeOptions[case] + commonOptions + unCommonOptions
        
        if not configs.get('closeDrivers'):
            print '\tFor: {}...\t'.format(case),; sys.stdout.flush()
            drivers[case].open(configs.get('browserPath'), chromeOptions[case], debugPorts[case])
            print 'Done'
     
    #Starting TCPDUMP
    if configs.get('tcpdump'):
        if configs.get('separateTCPDUMPs'):
            tcpdumpObj = None
        else:
            PRINT_ACTION('Starting TCPDUMP', 0)
            tcpdumpObj = TCPDUMP()
            print tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'], hosts=modifyEtcHosts.hosts)
    
    
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
    
    if configs.get('backgroundPings'):
        bgPingsFile = tcpdumpFile.rpartition('_')[0] + '_bgPings.txt'
        pingP = Ping()
        pingP.start(configs.get('host')['quic'], bgPingsFile)
        
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
                drivers[case].open(configs.get('browserPath'), chromeOptions[case], debugPorts[case])
            try:
                drivers[case].get(url, resultsDir + '/' + testID + '.har')
            except TimeoutError:
                    print 'Browser load timeout ({}) happend!!!'.format(browserLoadTimeout)
                    os.system('sudo pkill -f chrome-har-capturer')
                    time.sleep(5)
            except Exception as e:
                print '###### EXCEPTION during {}#######'.format(testID)
                print e
                traceback.print_exc()
                continue
            
            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpObj.stop()
             
            if configs.get('doStats'):
                statsRes = stat.stop()
                stat.save(statsDir+'/'+testID+'.json')
            
            if configs.get('closeDrivers'):
                drivers[case].close()
             
            time.sleep(configs.get('waitBetweenLoads'))

        if round != configs.get('rounds'):
            PRINT_ACTION('Sleeping between rounds: {} seconds ...'.format(configs.get('waitBetweenRounds')), 0)
            time.sleep(configs.get('waitBetweenRounds'))
        
#         raw_input('berim ?')
    
    PRINT_ACTION('Running final beforeExit ...', 0)
    if configs.get('backgroundPings'):
        pingP.stop()
    if configs.get('closeDrivers'):
        drivers=None
    if configs.get('separateTCPDUMPs'):
        tcpdumpObj=None
    beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=modifyEtcHosts, logName=logName, tcpprobePid=tcpprobePid)
    

if __name__=="__main__":
    main()
