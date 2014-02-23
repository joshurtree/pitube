import re
import types

class multire :
    def __init__(self, patterns) :
        self.patterns = patterns
        for i in range(len(self.patterns)) :
            if type(self.patterns[i]) == types.StringType :
                self.patterns[i] = re.compile(self.patterns[i])
        
    def __doAction(self, action) :
        for i in range(len(self.patterns)) :
            self.lastmatch = action(self.patterns[i])
            
            if self.lastmatch != None :
                return i
            
        return -1
        
    def match(self, value) :
        return self.__doAction(lambda pattern : pattern.match(value))
    
    def search(self, value) :
        return self.__doAction(lambda pattern : pattern.search(value))