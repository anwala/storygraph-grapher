import itertools

class GraphStories(object):
    
    #copied from genericCommon.py - start
    @staticmethod
    def jaccardFor2Sets(firstSet, secondSet):

        intersection = float(len(firstSet & secondSet))
        union = len(firstSet | secondSet)

        if( union != 0 ):
            return  round(intersection/union, 4)
        else:
            return 0

    @staticmethod
    def overlapFor2Sets(firstSet, secondSet):

        intersection = float(len(firstSet & secondSet))
        minimum = min(len(firstSet), len(secondSet))

        if( minimum != 0 ):
            return  round(intersection/minimum, 4)
        else:
            return 0

    @staticmethod
    def weightedJaccardOverlapSim(firstSet, secondSet, jaccardWeight):

        if( jaccardWeight > 1 ):
            jaccardWeight = 1
        elif( jaccardWeight < 0 ):
            jaccardWeight = 0

        overlapWeight = 1 - jaccardWeight

        jaccardWeight = jaccardWeight * GraphStories.jaccardFor2Sets(firstSet, secondSet)
        overlapWeight = overlapWeight * GraphStories.overlapFor2Sets(firstSet, secondSet)

        return jaccardWeight + overlapWeight

    @staticmethod
    def genWeightedJaccardOverlapSim(firstSet, secondSet, jaccardWeight=1, overlapWeight=1):

        denom = jaccardWeight + overlapWeight
        if( denom == 0 ):
            jaccardWeight = 1
            overlapWeight = 1

        return ((jaccardWeight * GraphStories.jaccardFor2Sets(firstSet, secondSet)) + (overlapWeight * GraphStories.overlapFor2Sets(firstSet, secondSet))) / denom
    #copied from genericCommon.py - end

    def __init__(self, storiesGraph, minSim, maxIteration, simDict):
        
        '''
            entityDict format: 
            {
                'entity': titleTerm,
                'class': 'TITLE',
                'source': sourceDictWithEntities['name'], 
                'link': website['link'], 
                'title': website['title'], 
                'published': website['published']
            }

            storiesGraph format:
            {
                "links":
                [
                ],
                "nodes":
                [
                    {
                        "id": "cnnLink-0",...,"entities": [{entityDict}]
                    },
                    {
                        "id": "foxLink",...,"entities": [{entityDict}]
                    },
                    ...
                ]
            }
        '''

        self.storiesGraph = storiesGraph        
        self.minSim = minSim
        self.maxIteration = maxIteration
        self.simDict = simDict

        if( 'similarity-metric' not in self.simDict ):        
            self.simDict['similarity-metric'] = 'overlap'        
                
        if( 'jaccard-weight' not in self.simDict ):        
            self.simDict['jaccard-weight'] = 0

        if( 'overlap-weight' not in self.simDict ):        
            self.simDict['overlap-weight'] = 1 - self.simDict['jaccard-weight']

        if( self.simDict['similarity-metric'] == 'size-sensitive-overlap' ):
            if( 'size-sensitive-overlap-weight' not in self.simDict ):
                self.simDict['size-sensitive-overlap-weight'] = 1

    def graphStories(self):
        print('graphStories():')

        '''
            get all pair keys
            calculate similarity of pair keys
            link pairs within minimum similarity 
        '''
        print('\tsimilarity-metric:', self.simDict['similarity-metric'])
        print('\tminSim:', self.minSim)
        print('\tmaxIteration:', self.maxIteration)

        indices = list( range( len(self.storiesGraph['nodes']) ) )        
        pairs = list( itertools.combinations(indices, 2) )

        for pair in pairs:
            
            firstStory = pair[0]
            secondStory = pair[1]
            
            entitiesAList = self.storiesGraph['nodes'][firstStory]['entities']
            entitiesBList = self.storiesGraph['nodes'][secondStory]['entities']
            
            sim, setDetailsDict = GraphStories.calcSingleSim(entitiesAList, entitiesBList, 'entity', self.simDict)
            
            if( sim >= self.minSim ):
                
                linkDict = {}
                linkDict['source'] = firstStory
                linkDict['target'] = secondStory
                linkDict['sim'] = round(sim, 2)
                linkDict['rank'] = -1

                self.storiesGraph['links'].append(linkDict)
                
                print('\tpairs:', firstStory, 'vs', secondStory)
                print('\t\tsim:', sim)
                print('\t\t', self.storiesGraph['nodes'][firstStory]['title'][:50] )
                print('\t\t', self.storiesGraph['nodes'][secondStory]['title'][:50] )
                print()

        #add ranks to links - start
        self.storiesGraph['links'] = sorted( self.storiesGraph['links'], key=lambda linkDict: linkDict['sim'], reverse=True )
        for i in range(0, len(self.storiesGraph['links'])):
            self.storiesGraph['links'][i]['rank'] = i+1
            #self.storiesGraph['links'][i]['label'] = str(i+1) + ' (' + str(self.storiesGraph['links'][i]['sim']) + ')'

        #add ranks to links - end

        print('pairs count:', len(pairs))

        return self.storiesGraph

    @staticmethod
    def extractSetFromCluster(cluster, extractionKey):

        clusterSet = set()
        for setMemberDict in cluster:

            if( setMemberDict['class'].upper() in ['DATE', 'PERCENT', 'MONEY'] ):
                #don't tokenize datetimes and percent and money
                clusterSet.add( setMemberDict[extractionKey].lower() )
            else:
                entityTokens = setMemberDict[extractionKey].lower().split(' ')
                for entityTok in entityTokens:
                    entityTok = entityTok.strip()
                    if( entityTok != '' ):
                        clusterSet.add( entityTok )

        return clusterSet

    @staticmethod
    def calcSingleSim(clusterA, clusterB, extractionKey, simDict):

        sim = 0
        
        #TOKENIZATION OPTIONS - start
        firstSet = GraphStories.extractSetFromCluster(clusterA, extractionKey)
        secondSet = GraphStories.extractSetFromCluster(clusterB, extractionKey)
        #TOKENIZATION OPTIONS - end

        
        setDetailsDict = {}

        if( simDict['similarity-metric'] == 'overlap' or simDict['similarity-metric'] == 'size-sensitive-overlap' ):
            sim = GraphStories.overlapFor2Sets(firstSet, secondSet)
        elif( simDict['similarity-metric'] == 'jaccard' ):
            sim = GraphStories.jaccardFor2Sets(firstSet, secondSet)
        elif( simDict['similarity-metric'] == 'weighted-jaccard-overlap' ):
            sim = GraphStories.weightedJaccardOverlapSim( firstSet, secondSet, jaccardWeight=simDict['jaccard-weight'] )
        else:
            print('\tGraphStories.calcSingleSim() - warning, no similarity metric:', simDict['similarity-metric'], 'found, similarity set to minimum (0)')

        return sim, setDetailsDict
