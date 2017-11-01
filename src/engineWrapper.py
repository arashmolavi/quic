'''
by: Arash Molavi Kakhki (arash@ccs.neu.edu)

This is a wrapper for engineChrome.

Example:
    python engineWrapper.py --networkInt=eth0 --rounds=2 --runQUICserver=False --runTcpProbe=False --against=GAE  --doIperf=False --chromium=False --xvfb=False --indexes=10KBx1,1MBx1  --tc=shape_loss_delay --rates=500mbit-500mbit,100mbit-100mbit --latency=50ms --burst=15k --lossArgs=0% --delayArgs=0ms  --quic-version=30 --testDir=testKir --browserPath=/opt/google/chrome/chrome
    python engineWrapper.py --networkInt=eth0 --rounds=2 --runQUICserver=False --runTcpProbe=False --against=GAE  --doIperf=False --chromium=False --xvfb=False --indexes=10KBx1,1MBx1  --tc=shape_loss_delay --rates=500mbit-500mbit,100mbit-100mbit --latency=50ms --burst=15k --lossArgs=0% --delayArgs=50ms --quic-version=30 --testDir=testKir --browserPath=/opt/google/chrome/chrome --doJitter=True --baseDelayDown=50 --varDelayDown=5 --baseDelayUp=50 --varDelayUp=5
    
    python engineWrapper.py --script2run=engineChrome_youtube.py --networkInt=eth0 --rounds=2 --doIperf=False --chromium=False --xvfb=False --tc=shape_loss_delay --rates=500mbit-500mbit,100mbit-100mbit --latency=50ms --burst=15k --lossArgs=0% --delayArgs=0ms --quic-version=30 --testDir=testKir --browserPath=/opt/google/chrome/chrome --qualities=hd2160,small --stopTime=10
'''

import sys, os, multiprocessing
from pythonLib import *
import doTCstuff


def initialize():
    configs = Configs()
    configs.set('rates'             , '5mbit-5mbit,25mbit-25mbit,100mbit-100mbit')
    configs.set('qualities'         , 'hd2160,hd1440,hd1080,hd720,large,medium,small,tiny,auto')
    configs.set('stopTime'          , '60')
    configs.set('indexes'           , '10MBx1')
    configs.set('networkInt'        , 'eth0')
    configs.set('rounds'            , 3)
    configs.set('tcpdump'           , True)
    configs.set('doSideTraffic'     , False)
    configs.set('runQUICserver'     , True)
    configs.set('runTcpProbe'       , False)
    configs.set('doJitter'          , False)
    configs.set('doIperf'           , False)
    configs.set('doPing'            , True)
    configs.set('xvfb'              , True)
    configs.set('closeDrivers'      , False)
    configs.set('clearCacheConns'   , True)
    configs.set('separateTCPDUMPs'  , False)
    configs.set('browserPath'       , False)
    configs.set('addPeakRate'       , False)
    configs.set('lossArgs'          , False)
    configs.set('delayArgs'         , False)
    configs.set('changeBW'          , False)
    configs.set('latencyOrLimit'    , 'latency')
    configs.set('against'           , '[your server name]')
    configs.set('quic_server_path'  , '')
    configs.set('script2run'        , 'engineChrome.py')
    
    configs.read_args(sys.argv)
    configs.show_all()
    
    if configs.get('xvfb'):
        configs.set('xvfb-run', 'xvfb-run')
    else:
        configs.set('xvfb-run', '')

    return configs

def run(configs):
    for rate in configs.get('rates').split(','):
        if configs.get('tc') == 'Nothing':
            dirName = configs.get('testDir')
        
        else:
            rateDown, rateUp = rate.split('-')
            
            print 'Doing: rate =', rateDown, rateUp
            
            if configs.get('lossArgs'):
                try:
                    lossArgsDown, lossArgsUp = configs.get('lossArgs').split('-')
                except ValueError:
                    lossArgsDown = configs.get('lossArgs')
                    lossArgsUp   = configs.get('lossArgs')
                finally:
                    lossArgsDown = lossArgsDown.split(',')
                    lossArgsUp   = lossArgsUp.split(',')
            else:
                lossArgsDown = False
                lossArgsUp   = False
                
            if configs.get('delayArgs'):
                try:
                    delayArgsDown, delayArgsUp = configs.get('delayArgs').split('-')
                except ValueError:
                    delayArgsDown = configs.get('delayArgs')
                    delayArgsUp   = configs.get('delayArgs')
                finally:
                    delayArgsDown = delayArgsDown.split(',')
                    delayArgsUp   = delayArgsUp.split(',')
            else:
                delayArgsDown = False
                delayArgsUp   = False
                 
            if configs.get('tc') == 'shape_loss_delay':
                if configs.get('tcWhere') == 'local':
                    doTCstuff.doShapeLossDelay( configs.get('networkInt'), 
                                                rateDown, rateUp, configs.get('latency'), configs.get('burst'), 
                                                lossArgsDown , lossArgsUp,
                                                delayArgsDown, delayArgsUp,
                                                addPeakRate=configs.get('addPeakRate') 
                                                )
            
                elif configs.get('tcWhere') == 'router':
                    #Changing TC config on router has to be done through SSH and it takes time! This mean I cannot do my own
                    #jitter thing, which is basically changing the delay at high frequency! (the frequency will be too low)
                    #So if I want to do my own jitter, I have to do the delay and delay change locally
                    #So if tcWhere is router, but we want to do my jitter, we have to do the delays locally
                    if configs.get('doJitter'):
                        tmpDelayArgsDown = False
                    else:
                        tmpDelayArgsDown = delayArgsDown
                        
                    doTCstuff.doShapeLossDelayRouter( rateDown, 
                                                      configs.get('burst'),
                                                      latency=configs.get('latency'),
                                                      latencyOrLimit=configs.get('latencyOrLimit'),
                                                      lossArgs=lossArgsDown,
                                                      delayArgs=tmpDelayArgsDown,
                                                      addPeakRate=configs.get('addPeakRate'),
                                                      interface=configs.get('networkInt'), 
                                    )
                print '\tTC on local:'
                doTCstuff.show(where='local')
                print '\tTC on router:'
                doTCstuff.show(where='router')
            
            if configs.get('changeBW'):
                doTCstuff.changeBW_router('start', configs.get('networkInt'), configs.get('baseBW'), configs.get('varBW'), configs.get('varBWsleep'))
                
            if configs.get('doJitter'):
                #See the comments above about why my jitter has to be done locally and cannot be done on the router
                if configs.get('tcWhere') == 'router':
                    doTCstuff.doDelay(configs.get('networkInt'), delayArgsDown, delayArgsUp)
    
                pJitter  = multiprocessing.Process(target=doTCstuff.addJitter, args=(configs.get('networkInt'), 
                                                                                     configs.get('baseDelayDown'), configs.get('varDelayDown'),
                                                                                     configs.get('baseDelayUp')  , configs.get('varDelayUp')
                                                                                    ),
                                                                               kwargs={'parent':'', 'handle':''})
    #             if configs.get('tcWhere') == 'local':
    #                 dirName = '-'.join( map(str, [configs.get('testDir'), configs.get('latency'), configs.get('burst'), 
    #                                               configs.get('lossArgs').replace(',', '-'),
    #                                               configs.get('delayArgs').replace(',', '-'),
    #                                               'jitter',
    #                                               str(configs.get('baseDelayDown')), str(configs.get('varDelayDown')), str(configs.get('baseDelayUp'))  , str(configs.get('varDelayUp')), 
    #                                               rateDown, rateUp]) )
    #                 
    #                 
    #                 pJitter  = multiprocessing.Process(target=doTCstuff.addJitter, args=(configs.get('networkInt'), 
    #                                                                                     configs.get('baseDelayDown'), configs.get('varDelayDown'),
    #                                                                                     configs.get('baseDelayUp')  , configs.get('varDelayUp')
    #                                                                                     ))
    #             elif configs.get('tcWhere') == 'router':
    #                 dirName = '-'.join( map(str, [configs.get('testDir'), configs.get('latency'), configs.get('burst'), 
    #                                               configs.get('lossArgs').replace(',', '-'),
    #                                               configs.get('delayArgs').replace(',', '-'),
    #                                               'jitter',
    #                                               str(configs.get('baseDelay')), str(configs.get('varDelay')), 
    #                                               rateDown]) )
    #                 
    #                 
    #                 pJitter  = multiprocessing.Process(target=doTCstuff.addJitterRouter, args=(configs.get('networkInt'), 
    #                                                                                            configs.get('baseDelayDown'), configs.get('varDelayDown'),
    #                                                                                            ))
                    
                pJitter.start()
                
            dirName = '-'.join( map(str, [configs.get('testDir'), configs.get('latency'), configs.get('burst')]))
            
            if configs.get('lossArgs'):
                dirName += '-' + configs.get('lossArgs').replace(',', '-')
                
            if configs.get('delayArgs'):
                dirName += '-' + configs.get('delayArgs').replace(',', '-')
            
            if configs.get('doJitter'):
                dirName += '-' + '-'.join(map( str, ['jitter', configs.get('baseDelayDown'), configs.get('varDelayDown'), configs.get('baseDelayUp'), configs.get('varDelayUp')]))
                
            if configs.get('changeBW'):
                dirName += '-' + '-'.join(map( str, ['varBW', configs.get('baseBW'), configs.get('varBW'), configs.get('varBWsleep')]))
            
            dirName += '-' + '-'.join( [rateDown, rateUp] )
        
        if configs.get('doIperf'):
            print 'Running iperf ...'
            if configs.get('against') == '[your server name]':
                iperfServer = "[iPerf should be running on the same host as QUIC/HTTPS server]"
            os.system('./do_iperf.sh {} {}'.format(dirName, iperfServer))
        
        if configs.get('doPing'):
            print 'Running pings ...'
            if configs.get('against') == '[your server name]':
                pingServer = "[QUIC/HTTPS server host address]"
            print './do_ping.sh {} {}'.format(dirName, pingServer)
            os.system('./do_ping.sh {} {}'.format(dirName, pingServer))
        
        if configs.get('script2run') == 'engineChrome_youtube.py':
            for desiredQuality in configs.get('qualities').split(','):
                print desiredQuality
                excludes = ['burst', 'runQUICserver', 'lossArgs', 'latency', 'doSideTraffic','tc', '000-scriptName', 'script2run', 'doJitter', 'runTcpProbe', 'clearCacheConn', 'serverIsLocal', 'addPeakRate', 'doPing', 'doIperf', 'delayArgs', 'against', 'quic_server_path', 'tcWhere', 'xvfb', 'rates', 'testDir', 'qualities', 'indexes']
#                 cmd  = '{} python {} {}'.format(configs.get('xvfb-run'), configs.get('script2run'), configs.serializeConfigs(exclude=['rates', 'testDir', 'qualities', 'indexes']))
                cmd  = '{} python {} {}'.format(configs.get('xvfb-run'), configs.get('script2run'), configs.serializeConfigs(exclude=excludes))
                cmd += '--testDir={}_{} --desiredQuality={}'.format(dirName, desiredQuality, desiredQuality)
                print cmd
                os.system(cmd)
        
        else:        
            for index in configs.get('indexes').split(','):
                cmd  = '{} python {} {}'.format(configs.get('xvfb-run'), configs.get('script2run'), configs.serializeConfigs(exclude=['rates', 'testDir', 'qualities', 'indexes']))
                cmd += '--testDir={}_{} --testPage=index_{}.html'.format(dirName, index, index)
                print '\tThe command:\n\t', cmd
                os.system(cmd)
        
        if configs.get('doJitter'):
            pJitter.terminate()
        
        if configs.get('changeBW'):
            doTCstuff.changeBW_router('stop', None, None, None, None)
            
        
    if configs.get('tc') != 'Nothing':
        PRINT_ACTION('Removing current TC configs', 0)
        doTCstuff.remove( configs.get('networkInt'), where=configs.get('tcWhere') )

def main():
    PRINT_ACTION('Reading configs file and args', 0)
    configs = initialize()

    PRINT_ACTION('Running...', 0)
    run(configs)
    
if __name__ == "__main__":
    main()
