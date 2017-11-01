'''
by: Arash Molavi Kakhki (arash@ccs.neu.edu)

Goal: run PLT tests on an android device connected via USB

IMPORTANT: running agianst my own QUIC server doesn't work because of certificate issues

Example:
    python engineAndroid_harCapturer.py --networkInt=en0 --against=EC2 --rounds=2 --testPage=index_100KBx1.html --testDir=test-phone --cases=quic,https
    python engineAndroid_harCapturer.py --networkInt=en0 --against=GCP --rounds=1 --quic_server_path=quic_server-52.0.2743.116-feb0ea45a0164eef52aa2631dd95d7c85fa65faa --testPage=index_100KBx1.html --testDir=kir --cases=quic
    
    python engineAndroid_harCapturer.py --networkInt=en0 --against=EC2 --rounds=2 --testPage=index_1MBx1.html --testDir=test-phone --cases=quic,https --runQUICserver=False --quic-version=30   
    
Some useful (!) adb commands:
    adb kill-server; pkill -f chromedriver; adb devices; chromedriver
    adb -s ZX1G22JSL7 shell getprop ro.product.model
    adb -s ZX1G22JSL7 shell getprop ro.build.version.release
    adb shell dumpsys netstats
    adb shell dumpsys cpuinfo
    adb shell dumpsys meminfo
    adb shell dumpsys connectivity
'''

import sys, subprocess, time, os, json
import stats
from pythonLib import *
from engineChrome import commandSimpleServer_runQuicServer_runTcpProbe, beforeExit, TCPDUMP, initialize
from engineAndroid import runADB
    
def portForward():
    os.system('adb forward tcp:9222 localabstract:chrome_devtools_remote')
    os.system('adb forward --list')

def removePortForward():
    os.system('adb forward --remove-all')

def singleLoad(url, chromeOptions, outFile, device, newChrome=True, blankAfter=True):
    if newChrome:
        #Close Chrome
        cmd = 'adb shell am force-stop com.android.chrome'
        os.system(cmd)
    
        #Set the options
        '''
        For MotoG, command line switches need to be writter to "/data/local/chrome-command-line" (and for writing to
        this file the device needs to be rooted, and the file should have chmod 777 permission!)
        
        For Nexus6 we can write the switches to "/data/local/tmp/chrome-command-line" which is not owned by root, hence
        the device doesn't need to be rooted
        
        See my Evernote notes on this: Rooting Android
        '''
        
        
        if device == 'MotoG':
            cmd = "adb shell 'echo \"chrome {}\" > /data/local/chrome-command-line'".format( ' '.join(chromeOptions) )
        else:
            cmd = "adb shell 'echo chrome {} > /data/local/tmp/chrome-command-line'".format( ' '.join(chromeOptions) )
            cmd = cmd.replace('"', '\\"')   #This is necessary to make sure qoutations are echoed correctly in the file 
        
        os.system(cmd)
        
        #Run Chrome
        cmd = 'adb shell am start com.android.chrome/com.google.android.apps.chrome.Main'
        os.system(cmd)
        time.sleep(5)

    #Load the URL
    cmd = ['chrome-har-capturer', '--force', '--give-up', '60', '--port', '9222', '-o', outFile, url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    communication = p.communicate()
    print communication
    
    #Print result
    try:
        with open(outFile, 'r') as f:
            j = json.load(f)
            print '\t\t', j['log']['pages'][0]['pageTimings']['onLoad']
    except:
        pass
    
    if blankAfter:
        #Load a blank page so next time Chrome is openned the URL is not loaded again
        cmd = ['chrome-har-capturer', '--force', '--give-up', '1', '--port', '9222', '-o', '/tmp/dummy', 'about:blank']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        communication = p.communicate()
     
def main():
    os.system('sudo echo;')
    
    PRINT_ACTION('Reading configs file and args', 0)
    configs, cases, methods, testDir, resultsDir, statsDir, userDirs, screenshotsDir, dataPaths, netLogs, tcpdumpDir, tcpdumpFile, uniqeOptions, modifyEtcHosts = initialize()
    configs.show_all()

    drivers=None
    
    device = runADB()
    portForward()
    
    PRINT_ACTION('Creating driver options ...', 0)
    chromeOptions = {}
    commonOptions = []
    if configs.get('clearCacheConns'):
        commonOptions += ['--enable-benchmarking', '--enable-net-benchmarking']
    #Because I have to use "echo" and "adb shell" to write to a file when setting flags for Chrome on Android,
    #I need quotations and escapes and stuff. SO the "host-resolver-rule" option's quoatation for mobile is different
    uniqeOptions['quic-proxy'] = uniqeOptions['quic-proxy-mobile']
    
    for case in cases:
#         unCommonOptions     = ['--user-data-dir=/data/user/0/com.android.chrome/app_chrome/kirUserDir/{}'.format(case),
#                                '--data-path=/data/user/0/com.android.chrome/app_chrome/kirDataPath/{}'.format(case),
#                                ]
        unCommonOptions     = []
        chromeOptions[case] = uniqeOptions[case] + unCommonOptions + commonOptions
        
    
    #Starting TCPDUMP
    if configs.get('tcpdump'):
        if configs.get('separateTCPDUMPs'):
            tcpdumpObj = None
        else:
            PRINT_ACTION('Starting TCPDUMP', 0)
            tcpdumpObj = TCPDUMP()
            tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'], hosts=None)
    

    #Asking remote host to start QUIC server
    logName     = False
    tcpprobePid = False
    if not configs.get('against') == 'GAE':
        if configs.get('runQUICserver') and ('quic' in cases):
            PRINT_ACTION('Asking remote host to start QUIC server', 0)
            logName  = '_'.join(['quic_server_log', testDir.rpartition('/')[2], configs.get('testPage')]) + '.log'
            
            exitCode = commandSimpleServer_runQuicServer_runTcpProbe('start_quicServer', logName=logName, host=configs.get('host')['quic'], quic_server_path=configs.get('quic_server_path'))
            
            PRINT_ACTION('Done: ' + str(exitCode), 2, action=False)
            if exitCode == -13:
                beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=None, logName=logName)
                sys.exit()
        
        
        #Asking remote host to start runTcpProbe
        if configs.get('runTcpProbe'):
            PRINT_ACTION('Asking remote host to start tcpprobe', 0)
            logNameTCP  = '_'.join(['tcpprobe_log', testDir.rpartition('/')[2], configs.get('testPage')]) + '.log'
            tcpprobePid = commandSimpleServer_runQuicServer_runTcpProbe('start_tcpprobe', logName=logNameTCP, host=configs.get('host')['https'])
            PRINT_ACTION('Done: ' + str(tcpprobePid), 2, action=False)
            if tcpprobePid == -13:
                beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=None, logName=logName, tcpprobePid=tcpprobePid)
                sys.exit()

    
    if configs.get('doStats'):
        stat = stats.AndroidStats()
    
    for round in range(1, configs.get('rounds')+1):
        for case in cases:
            testID = '{}_{}'.format(case, round)
            print '\tDoing: {}/{}'.format(testID, configs.get('rounds'))
            
            if case.startswith('quic') and (not (configs.get('against') == 'GAE')):
                url = '{}://{}/{}'.format(methods[case], configs.get('host')[case], configs.get('testPage'), testID)
            else:
                url = '{}://{}/?page={}&testID={}'.format(methods[case], configs.get('host')[case], configs.get('testPage'), testID)
            
            if configs.get('doStats'):
                stat.start()
            
            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpFile = tcpdumpDir + '/' + testID + '.pcap'
                tcpdumpObj = TCPDUMP()
                tcpdumpObj.start(tcpdumpFile, interface=configs.get('networkInt'), ports=['80', '443'], hosts=modifyEtcHosts.hosts)
            
            if case == 'quic' and configs.get('doSecondDL'):
                singleLoad(url, chromeOptions[case], resultsDir + '/' + testID + '.har_1st' , device, newChrome=True    , blankAfter=False)
                singleLoad(url, chromeOptions[case], resultsDir + '/' + testID + '.har'     , device, newChrome=False   , blankAfter=True)
            else:
                singleLoad(url, chromeOptions[case], resultsDir + '/' + testID + '.har'     , device, newChrome=True    , blankAfter=True)
            
            if configs.get('separateTCPDUMPs') and configs.get('tcpdump'):
                tcpdumpObj.stop()
            
            if configs.get('doStats'):
                stat.stop()
                stat.save(statsDir+'/'+testID+'.json')
                
            time.sleep(configs.get('waitBetweenLoads'))

        if round != configs.get('rounds'):
            PRINT_ACTION('Sleeping between rounds: {} seconds ...'.format(configs.get('waitBetweenRounds')), 0)
            time.sleep(configs.get('waitBetweenRounds'))
            
    PRINT_ACTION('Running final beforeExit ...', 0)
    #Remove adb port forwarding
    removePortForward()
    
    #Close Chrome
    cmd = 'adb shell am force-stop com.android.chrome'
    os.system(cmd)
    
    #The usual before Exit
    if configs.get('separateTCPDUMPs'):
        tcpdumpObj=None
    beforeExit(tcpdumpObj=tcpdumpObj, drivers=drivers, modifyEtcHosts=None, logName=logName, tcpprobePid=tcpprobePid)
    
        
if __name__=="__main__":
    main()
