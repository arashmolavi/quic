'''
by: Arash Molavi Kakhki (arash@ccs.neu.edu)

Note:    The extension is responsible for clearing the cache before navigation starts
         (see background.js in extension_cache_remover folder)

Example:
    python engineChrome_youtube.py --testDir=YouTubeQoE --networkInt=en5  --rounds=2 --stopTime=5 --desiredQuality=hd720 --closeDrivers=True  --separateTCPDUMPs=True --platform=mac     --browserPath="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    python engineChrome_youtube.py --testDir=YouTubeQoE --networkInt=eth0 --rounds=2 --stopTime=5 --desiredQuality=hd720 --closeDrivers=True  --separateTCPDUMPs=True --platform=linux64 --browserPath=/home/arash/Release-52.0.2743.116-feb0ea45a0164eef52aa2631dd95d7c85fa65faa/chrome
    python engineChrome_youtube.py --testDir=YouTubeQoE --networkInt=eth0 --rounds=2 --stopTime=5 --desiredQuality=hd720 --closeDrivers=False --separateTCPDUMPs=True
    
Acceptable qualities: hd2160, hd1440, hd1080, hd720, large, medium, small, tiny, auto
'''

import sys, os, time, pickle, socket, json, subprocess, traceback
import stats
import sideTrafficGenerator
from selenium import webdriver
from pythonLib import *
from engineChrome import TCPDUMP, Driver, selectChromeDriverPath, ModifyEtcHosts
from engineChrome import TimeoutError
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

def initialize():
    configs = Configs()
    
    configs.set('serverIsLocal'     , False)
    configs.set('waitBetweenLoads'  , 1)
    configs.set('waitBetweenRounds' , 1)
    configs.set('rounds'            , 10)
    configs.set('pageLoadTimeout'   , 60*60)
    configs.set('tcpdump'           , True)
    configs.set('browserPath'       , False)
    configs.set('closeDrivers'      , True)
    configs.set('separateTCPDUMPs'  , False)
    configs.set('stopTime'          , 5)
    configs.set('desiredQuality'    , 'hd720')
    configs.set('mainDir'           , os.path.abspath('../data') + '/results')
    configs.set('extPath'           , os.path.abspath('extension_cache_remover'))
    
    configs.read_args(sys.argv)
    
    configs.set('chromedriver', selectChromeDriverPath(configs.get('browserPath'), configs.get('platform')))
    
    '''
    Important: the following MUST be done AFTRE read_args in case "againstAppEngine" gets overridden 
    '''
    configs.check_for(['testDir', 'networkInt'])
    
    if configs.get('testDir').endswith('/'):
        configs.set( 'testDir', configs.get('testDir')[:-1] )
    
    configs.set('testDir', configs.get('mainDir') + '/' + configs.get('testDir') )
    
    if os.path.isdir(configs.get('testDir')):
        print 'Test directory already exists! Use another name!'
        sys.exit()

    #Setting up the browser path. I usually have multiple instances of chrome/chromium on the client machine,
    #so it's important to specify the path chromedriver should use.
    if configs.get('browserPath'):
        webdriver.ChromeOptions.binary_location = configs.get('browserPath')
        
#     if os.path.isfile(configs.get('chromedriverPath')['default']):
#         configs.set('chromedriver', configs.get('chromedriverPath')['default'])
#     elif os.path.isfile(configs.get('chromedriverPath')['fallback']):
#         configs.set('chromedriver', configs.get('chromedriverPath')['fallback'])
            
    return configs

def beforeExit(tcpdumpObj=None, drivers=None, modifyEtcHosts=None):
    
    configs = Configs()
    
    #Killing TCPDUMP
    if tcpdumpObj:
        PRINT_ACTION('Killing TCPDUMP', 0)
        if configs.get('tcpdump'):
            tcpdumpObj.stop()

    #Closing drivers
    if drivers:
        PRINT_ACTION('Closing drivers', 0)
        for case in drivers:
            try:
                drivers[case].close()
            except TimeoutError:
                print 'Got stuck closing drivers! :-s'
     
    if modifyEtcHosts:
        PRINT_ACTION('Reverting modifications to /etc/hosts', 0)
        modifyEtcHosts.remove( [ 'googlevideo.com' ] )
     
    time.sleep(3)
        
def main():
    #The following line is to make sure the script has sudo privilage to run tcpdump
    os.system('sudo echo')


    #Setting up configs
    PRINT_ACTION('Reading configs file and args', 0)
    configs        = initialize()
    configs.show_all()
    
    
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
    tcpdumpFile     = '{}/tcpdump.pcap'.format(testDir)
      
    os.system('mkdir -p {}'.format(resultsDir))
    os.system('mkdir -p {}'.format(statsDir))
    os.system('mkdir -p {}'.format(userDirs))
    os.system('mkdir -p {}'.format(screenshotsDir))
    os.system('mkdir -p {}'.format(dataPaths))
    os.system('mkdir -p {}'.format(netLogs))
    os.system('mkdir -p {}'.format(tcpdumpDir))
    
    
    #Creating options
    PRINT_ACTION('Creating options', 0)
    cases         = ['quic', 'https']
    methods       = {'quic':'https', 'https':'https'}
    commonOptions = ['--load-extension={}'.format(configs.get('extPath'))]
    chromeOptions = {}
    drivers       = {}
    stat          = stats.Stats(netInt=configs.get('networkInt'))
    uniqeOptions  = {'quic' : [
                               '--enable-quic',
#                                '--origin-to-force-quic-on={}'.format('googlevideo.com:443,youtube.com:443,google.com:443'),
#                                '--quic-host-whitelist={}'.format('googlevideo.com,youtube.com,google.com'),
                               '--origin-to-force-quic-on={}'.format('googlevideo.com:443'),
                               '--quic-host-whitelist={}'.format('googlevideo.com'),
                               '--no-proxy-server',
#                                "--host-resolver-rules='MAP {}:443 {}:443'".format(configs.get('host')['quic'], configs.get('host')['quic'])
                              ],
                     'https': [
                               '--disable-quic',
                              ],               
                    }

    try:
        configs.get('quic-version')
        uniqeOptions['quic'].append( '--quic-version=QUIC_VERSION_{}'.format(configs.get('quic-version')) )
    except KeyError:
        pass
        
    #Creating driver instances and modifying /etc/hosts
    PRINT_ACTION('Creating driver instances and modifying /etc/hosts', 0)
    modifyEtcHosts = ModifyEtcHosts()
    modifyEtcHosts.add(['googlevideo.com'])
#     modifyEtcHosts.show()
    
    for case in cases:
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
            tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'])
                
    
    #Firing off the tests
    PRINT_ACTION('Firing off the tests', 0)
    for round in range(1, configs.get('rounds')+1):
        for case in cases:
            testID = '{}_{}'.format(case, round)
            url    = 'file:///' + os.path.abspath('.') + '/youtubePlayerStats.html?stoptime={}&quality={}'.format( configs.get('stopTime'), configs.get('desiredQuality') )
 
#             stat.start()

            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpFile = tcpdumpDir + '/' + testID + '.pcap'
                tcpdumpObj = TCPDUMP()
                tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'])

            maxTries    = 3
            maxTryTime  = 2*configs.get('stopTime')
            tryN        = 0
            tryT        = 0
            stopped     = False
            
            while (tryN < maxTries) and (not stopped):
                tryN += 1
                PRINT_ACTION('Doing: {} (try:{})'.format(testID, tryN), 1, action=False)
                
                if configs.get('closeDrivers'):
                    PRINT_ACTION('Opening driver: '+ testID, 2, action=False)
                    try:
                        drivers[case].open()
                    except TimeoutError:
                        print 'Got stuck opening driver! :-s'
                        continue
                
                try:
                    drivers[case].get(url)
                    drivers[case].driver.find_element_by_id('player').click()
                except Exception as e:
                    print '###### EXCEPTION during {}#######'.format(testID)
                    print e
                    traceback.print_exc()
                    continue
                
                
                stopped = drivers[case].driver.execute_script("return stopped;")
                while (not stopped) and (tryT < maxTryTime):
                    tryT += 1
                    print '.',; sys.stdout.flush()
                    time.sleep(1)
                    stopped = drivers[case].driver.execute_script("return stopped;")
            
            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpObj.stop()
            
            results = drivers[case].driver.execute_script("return window.arashResults;")
            print results
             
            with open(resultsDir + '/' + testID + '.json', "w") as f:
                json.dump( {'results' : results, 'testID' : testID}, f )
             
#             statsRes = stat.stop()
#             stat.save(statsDir+'/'+testID+'.json')
            
            drivers[case].driver.save_screenshot('{}/{}.png'.format(screenshotsDir, testID))
            
            if configs.get('closeDrivers'):
                try:
                    drivers[case].close()
                except TimeoutError:
                    print 'Got stuck closing driver! :-s'
             
            time.sleep(configs.get('waitBetweenLoads'))
            
#             raw_input('berim ?')
         
        if round != configs.get('rounds'):
            time.sleep(configs.get('waitBetweenRounds'))
        
#         raw_input('berim ?')

    PRINT_ACTION('Running final beforeExit ...', 0)
    if configs.get('closeDrivers'):
        drivers=None
    if configs.get('separateTCPDUMPs'):
        tcpdumpObj=None    
    beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=modifyEtcHosts)
    
if __name__=="__main__":
    main()
