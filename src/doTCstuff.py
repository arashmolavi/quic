'''
by: Arash Molavi Kakhki (arash@ccs.neu.edu)

Example:
    python doTCstuff.py --what=del --where=local  --interface=eth0
    python doTCstuff.py --what=none               --interface=eth0 --rateDown=100mbit --rateUp=100mbit --latency=50ms --burst=15k --lossArgs=0%,25% --delayArgs=50ms      --outFile=jitter_none.txt  --doJitter=False
    python doTCstuff.py --what=shape_loss_delay   --interface=eth0 --rateDown=100mbit --rateUp=100mbit --latency=50ms --burst=15k --lossArgsDown=0% --lossArgsUp=0% --delayArgsDown=50ms --delayArgsUp=50ms  --doPings=False  --doJitter=False
    python doTCstuff.py --what=shape_loss_delay   --interface=eth0 --rateDown=100mbit --rateUp=100mbit --latency=50ms --burst=15k --lossArgsDown=0% --lossArgsUp=0% --delayArgsDown=50ms --delayArgsUp=50ms --doJitter=True --baseDelayDown=50 --varDelayDown=5 --baseDelayUp=50 --varDelayUp=5 --doPings=True --outFile=jitter_mine.txt
    
    python doTCstuff.py --what=del --where=router --interface=eth0
    
    python doTCstuff.py --what=shape_loss_delay_router --interface=eth0 --rate=100mbit --latency=50ms --burst=15k --addPeakRate=False --lossArgs=0% --delayArgs=50ms
'''

import sys, os, random, time, multiprocessing, subprocess
from pythonLib import *

def fixProxyDelays(delay, serverIP, interface='eth0', ifb='ifb0'):
    addIngressInterface(interface, ifb)
    os.system('sudo tc qdisc  add dev {} root handle 1: prio'.format(interface))
    os.system('sudo tc qdisc  add dev {} parent 1:1 handle 2: netem delay {}'.format(interface, delay))
    os.system('sudo tc filter add dev {} parent 1:0 protocol ip pref 55 handle ::55 u32 match ip dst {} flowid 2:1'.format(interface, serverIP))
    
    os.system('sudo tc qdisc  add dev {} root handle 1: prio'.format(ifb))
    os.system('sudo tc qdisc  add dev {} parent 1:1 handle 2: netem delay {}'.format(ifb, delay))
    os.system('sudo tc filter add dev {} parent 1:0 protocol ip pref 55 handle ::55 u32 match ip src {} flowid 2:1'.format(ifb, serverIP))

def addIngressInterface(interface, ifb):
    os.system('sudo modprobe ifb numifbs=1')
    os.system('sudo ip link set dev {} up'.format(ifb))
    os.system('sudo tc qdisc add dev {} handle ffff: ingress'.format(interface))
    os.system('sudo tc filter add dev {} parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev {}'.format(interface, ifb))

def remove(interface, ifb='ifb0', where='local'):
    if where == 'local':
        print 'Removing current tc stuff on {}...'.format(where)
        os.system('sudo tc qdisc del dev {} handle ffff: ingress'.format( interface ))
        os.system('sudo tc qdisc del dev {} root'.format( interface ))
        os.system('sudo tc qdisc del dev {} root'.format( ifb ))
        os.system('sudo ip link set dev {} down'.format( ifb ))

    elif where == 'router':
        os.system("ssh router 'tc qdisc del dev {} root'".format(interface))

def show(where='local'):
    print 'TC on {}:'.format(where)
    if where == 'local':
        os.system('sudo tc qdisc show')
    
    elif where == 'router':
        os.system("ssh router 'tc qdisc show'")

def doDelay(interface, delayArgsDown, delayArgsUp, ifb='ifb0'):
    remove(interface, ifb=ifb, where='local')
    
    addIngressInterface(interface, ifb)
      
    os.system('sudo tc qdisc add dev {} root netem delay {}'.format(interface, ' '.join(delayArgsUp)))
    os.system('sudo tc qdisc add dev {} root netem delay {}'.format(ifb      , ' '.join(delayArgsDown)))
        
def doShapeLossDelay(interface, rateDown, rateUp, latency, burst, lossArgsDown, lossArgsUp, delayArgsDown, delayArgsUp, ifb='ifb0', addPeakRate=False):    
    remove(interface, ifb=ifb, where='local')
    print interface, rateDown, rateUp, latency, burst, lossArgsDown, lossArgsUp, delayArgsDown, delayArgsUp     
    addIngressInterface(interface, ifb)
     
    peakRateUp   = str(float(rateUp.partition('mbit')[0])   + 0.1) + 'mbit'
    peakRateDown = str(float(rateDown.partition('mbit')[0]) + 0.1) + 'mbit'
     
    if addPeakRate:
        os.system('sudo tc qdisc add dev {} root    handle 1: tbf rate {} latency {} burst {} peakrate {} minburst 1540'.format(interface, rateUp, latency, burst, peakRateUp))
    else:
        os.system('sudo tc qdisc add dev {} root    handle 1: tbf rate {} latency {} burst {}'.format(interface, rateUp, latency, burst))
	print '1:', 'sudo tc qdisc add dev {} root    handle 1: tbf rate {} latency {} burst {}'.format(interface, rateUp, latency, burst)
   
    if lossArgsUp:
        if type(lossArgsUp) is list:
            lossArgsUp = ' '.join(lossArgsUp)
        os.system('sudo tc qdisc add dev {} parent 1:1  handle 10: netem loss  '.format(interface) + ' '.join(lossArgsUp)  )
	print '2:', 'sudo tc qdisc add dev {} parent 1:1  handle 10: netem loss  '.format(interface) + ' '.join(lossArgsUp)  
    
    if delayArgsUp:
        if not lossArgsUp:
	    print 'kir'
            parent = '1:'
            handle = '10:'
        else:
	    print 'kos'
            parent = '10:'
            handle = '20:'
        
        if type(delayArgsUp) is list:
            delayArgsUp = ' '.join(delayArgsUp)
        os.system('sudo tc qdisc add dev {} parent {} handle {} netem delay {}'.format(interface, parent, handle, delayArgsUp))
	print '3:','sudo tc qdisc add dev {} parent {} handle {} netem delay {}'.format(interface, parent, handle, delayArgsUp)

 
    if addPeakRate:
        os.system('sudo tc qdisc add dev {} root    handle 1: tbf rate {} latency {} burst {} peakrate {} minburst 1540'.format(ifb, rateDown, latency, burst, peakRateDown))
    else:
        os.system('sudo tc qdisc add dev {} root    handle 1: tbf rate {} latency {} burst {}'.format(ifb, rateDown, latency, burst))
     
    
    if lossArgsDown:
        if type(lossArgsDown) is list:
            lossArgsDown = ' '.join(lossArgsDown)
	os.system('sudo tc qdisc add dev {} parent 1:1  handle 10: netem loss {}'.format(ifb, lossArgsDown))
    
    if delayArgsDown:
        if not lossArgsDown:
            parent = '1:'
            handle = '10:'
        else:
            parent = '10:'
            handle = '20:'

        if type(delayArgsDown) is list:
            delayArgsDown = ' '.join(delayArgsDown)
        
        os.system('sudo tc qdisc add dev {} parent {} handle {} netem delay {}'.format(ifb, parent, handle, delayArgsDown))

def doShapeLossDelayRouter(rate, burst, latency, latencyOrLimit='latency', lossArgs=False, delayArgs=False, interface='eth0', addPeakRate=False):
    #Remove any previous tc ruls
    remove(interface, where='router')
    
    #Add rate rules
    if addPeakRate:
        if 'mbit' in rate:
            p = 'mbit'
        peakRate = str(float(rate.partition(p)[0])   + 0.1) + p
        
        tcCmd = "'tc qdisc add dev {} root handle 1: tbf rate {} {} {} burst {} peakrate {} minburst 1540'".format(interface, rate, latencyOrLimit, latency, burst, peakRate)
    else: 
        tcCmd = "'tc qdisc add dev {} root handle 1: tbf rate {} {} {} burst {}'".format(interface, rate, latencyOrLimit, latency, burst)
        
    os.system('ssh router {}'.format(tcCmd))

    #Add loss rules
    if lossArgs:
        if type(lossArgs) is list:
            lossArgs = ' '.join(lossArgs)
            
        tcCmd = "'tc qdisc add dev {} parent 1:  handle 10: netem loss {}'".format(interface, lossArgs)
        os.system('ssh router {}'.format(tcCmd))
    
    #Add delay rules
    if delayArgs:
        if not lossArgs:
            parent = '1:'
            handle = '10:'
        else:
            parent = '10:'
            handle = '20:'
        
        if type(delayArgs) is list:
            delayArgs = ' '.join(delayArgs)
            
        tcCmd = "'tc qdisc add dev {} parent {} handle {} netem delay {}'".format(interface, parent, handle, delayArgs)
        os.system('ssh router {}'.format(tcCmd))

def changeBW_router(what, interface, baseBW, varBW, sleep):
    if what == 'start':
        tcCmd = "'./bandwidth_oscillator_on_router.sh {} {} {} {}  > /dev/null 2>&1 &'".format(interface, baseBW, varBW, sleep)
        os.system('ssh router {}'.format(tcCmd))
    if what == 'stop':
        tcCmd = "\"ps | grep band |  awk '{ print $1}' | xargs kill -9\""
        os.system('ssh router {}'.format(tcCmd))
        
def changeDelay(interface, ifb, delayDown, delayUp, parent='', handle=''):
    if parent:
        parent = 'parent {}'.format(parent)
    if handle:
        handle = 'handle {}'.format(handle)
    if (not parent) and (not handle):
	parent = 'root'
    
    os.system('sudo tc qdisc change dev {} {} {} netem delay {}'.format(interface, parent, handle, ' '.join(delayUp) ))
    os.system('sudo tc qdisc change dev {} {} {} netem delay {}'.format(ifb      , parent, handle, ' '.join(delayDown) ))
    
def changeDelayRouter(interface, delay, parent='1:0', handle='10:'):
    tcCmd = 'tc qdisc change dev {} parent {} handle {} netem delay {}'.format(interface, parent, handle, ' '.join(delay) )
    os.system('ssh router {}'.format(tcCmd))

def addJitter(interface, baseDelayDown, varDelayDown, baseDelayUp, varDelayUp, ifb='ifb0', interval=0.1, parent='10:1', handle='20:'):
    counter       =  0
    prevDelayDown = -1
    prevDelayUp   = -1

    while True:
        counter += 1
        if baseDelayDown == 0:
            delayDown = 0
        else:
            delayDown = random.randrange(baseDelayDown-varDelayDown, baseDelayDown+varDelayDown)
        if baseDelayUp == 0:
            delayUp = 0
        else:
            delayUp   = random.randrange(baseDelayUp-varDelayUp, baseDelayUp+varDelayUp)
                
        if (delayDown < prevDelayDown) or (delayUp < prevDelayUp):
            steps = 2
            gapDown = prevDelayDown - delayDown
            gapUp   = prevDelayUp   - delayUp
             
            for i in range(1, steps+1):
                tmpDelayDown = prevDelayDown - i*gapDown/steps
                tmpDelayUp   = prevDelayUp - i*gapUp/steps
                
                changeDelay( interface, ifb, [str(tmpDelayDown) + 'ms'], [str(tmpDelayUp) + 'ms'], parent=parent, handle=handle)
                time.sleep(interval/steps)
        else:
            changeDelay( interface, ifb, [str(delayDown) + 'ms'], [str(delayUp) + 'ms'], parent=parent, handle=handle)
            time.sleep(interval)
        
        prevDelayDown = delayDown
        prevDelayUp   = delayUp

def addJitterRouter(interface, baseDelay, varDelay, interval=0.1):
    counter       =  0
    prevDelayDown = -1

    while True:
        counter += 1
        if baseDelay == 0:
            delay = 0
        else:
            delay = random.randrange(baseDelay-varDelay, baseDelay+varDelay)
        if baseDelayUp == 0:
            delayUp = 0
        else:
            delayUp   = random.randrange(baseDelayUp-varDelayUp, baseDelayUp+varDelayUp)
        
        if (delay < prevDelay):
            steps = 2
            gap = prevDelay - delay
             
            for i in range(1, steps+1):
                tmpDelay = prevDelay - i*gap/steps
                
                changeDelayRouter( interface, [str(tmpDelay) + 'ms'])
                time.sleep(interval/steps)
        else:
            changeDelayRouter( interface, [str(delay) + 'ms'] )
            time.sleep(interval)
        
        prevDelay = delay
    
def main():
    pass    

if __name__ == '__main__':
    main()
