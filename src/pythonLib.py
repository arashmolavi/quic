import subprocess, ConfigParser, sys

class TCPDump(object):
    def __init__(self, outFile, interface='en0', bufferSize=131072, host=None):
        self.interface  = interface
        self.bufferSize = bufferSize
        self.outFile    = outFile
        self.host       = host
        
    def start(self):
        command = ['tcpdump', '-nn', '-B', str(self.bufferSize), '-i', self.interface, '-w', self.outFile]
#         command = ['tcpdump', '-w', self.outFile]
        print ' '.join(command)
        
        if self.host is not None:
            command += ['host', self.host]
        
        self.p = subprocess.Popen(command)
#         self.p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
    def stop(self):
        output = ['-1', '-1', '-1']
        
        try:
            self.p.terminate()
            output = self.p.communicate()
            print output
            output = map(lambda x: x.partition(' ')[0], output[1].split('\n')[1:4])
        except AttributeError:
            return

        return output

def PRINT_ACTION(message, indent, action=True, exit=False, newLine=True):
    if action:
        print ''.join(['\t']*indent), '[' + str(Configs().action_count) + ']' + message , ' ' 
#         if newLine:
#             print '\n'
#         else:
#             sys.stdout.flush()
        Configs().action_count = Configs().action_count + 1
    elif exit is False:
        print ''.join(['\t']*indent) + message
    else:
        print '\n***** Exiting with error: *****\n', message, '\n***********************************\n'
        sys.exit()

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Configs(object):
    '''
    This object holds all configs
    
    BE CAREFUL: it's a singleton!
    '''
    __metaclass__ = Singleton
    _Config  = None
    _configs = {}
    def __init__(self, config_file = None):
        self._Config = ConfigParser.ConfigParser()
        self.action_count = 1
        self._maxlen = 0
        if config_file != None:
            read_config_file(config_file)
    def read_config_file(self, config_file):
        with open(config_file, 'r') as f:
            while True:
                try:
                    l = f.readline().strip()
                    if l == '':
                        break
                except:
                    break
                
                a = l.partition('=')
                
                if a[2] in ['True', 'true']:
                    self.set(a[0], True)
                elif a[2] in ['False', 'false']:
                    self.set(a[0], False)
                else:
                    try:
                        self.set(a[0], int(a[2]))
                    except ValueError:
                        try:
                            self.set(a[0], float(a[2]))
                        except ValueError:
                            self.set(a[0], a[2])
    def read_args(self, args):
        self.set('000-scriptName', args[0])
        for arg in args[1:]:
            a = ((arg.strip()).partition('--')[2]).partition('=')
            
            if a[0] == 'ConfigFile':
                self.read_config_file(a[2])
            
            if a[2] in ['True', 'true']:
                self.set(a[0], True)
            
            elif a[2] in ['False', 'false']:
                self.set(a[0], False)
            
            else:
                try:
                    self.set(a[0], int(a[2]))
                except ValueError:
                    try:
                        self.set(a[0], float(a[2]))
                    except ValueError:
                        self.set(a[0], a[2])
#         if 'ConfigFile' in self._configs:
#             self.read_config_file(self._configs['ConfigFile'])
    def serializeConfigs(self, exclude=[]):
        serialized = ''
        for key in self._configs:
            if key in exclude:
                continue
            else:
                serialized += '--' + key + '=' + str(self._configs[key]) + ' '
        return serialized
    def check_for(self, list_of_mandotary):
        try:
            for l in list_of_mandotary:
                self.get(l)
        except:
            print '\nYou should provide \"--{}=[]\"\n'.format(l)
            sys.exit(-1) 
    def get(self, key):
        return self._configs[key]
    def is_given(self, key):
        try:
            self._configs[key]
            return True
        except:
            return False
    def set(self, key, value):
        self._configs[key] = value
        if len(key) > self._maxlen:
            self._maxlen = len(key)
    def show(self, key):
        print key , ':\t', value
    def show_all(self):
        for key in sorted(self._configs):
            print '\t', key.ljust(self._maxlen) , ':', self._configs[key]
    def write2file(self, filename):
        with open(filename, 'w') as f:
            for key in sorted(self._configs):
                f.write('{}\t{}\n'.format(key, self._configs[key]))
    def __str__(self):
        return str(self._configs)
    def reset_action_count(self):
        self._configs['action_count'] = 0
    def reset(self):
        _configs = {}
        self._configs['action_count'] = 0

