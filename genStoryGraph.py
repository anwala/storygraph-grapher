#!/usr/bin/env python

import argparse
import copy
import feedparser
import graphAnnotate
import gzip
import importlib
import json
import math
import os
import sys
import time

from datetime import datetime
from GraphStories import GraphStories
from multiprocessing import Pool
from os.path import dirname, abspath
from random import randint
from subprocess import check_output

from util import archiveNowProxy
from util import clean_html
from util import dereferenceURI
from util import dumpJsonToFile
from util import expandUrl
from util import extractFavIconFromHTML
from util import extractPageTitleFromHTML
from util import genericErrorInfo
from util import getConfigParameters
from util import getDedupKeyForURI
from util import getDictFromFile
from util import getDomain
from util import getEntitiesFromText
from util import getFromDict
from util import getHashForText
from util import getISO8601Timestamp
from util import getTopKTermsListFromText
from util import getURIHash
from util import isExclusivePunct
from util import isStopword
from util import nlpGetEntitiesFromText
from util import nlpIsServerOn
from util import nlpServerStartStop
from util import parseStrDate
from util import readTextFromFile
from util import sanitizeText
from util import setInDict
from util import writeTextToFile

globalConfig = {'graphName': ''}
#experiment - start
#experiment - end

def localErrorHandler():
    
    logFolder = ''
    errorFile = ''

    if( len(globalConfig['graphName']) != 0 ):
        logFolder = f'{args.data_path}logs/' + globalConfig['graphName'] + '/'
        os.makedirs(logFolder, exist_ok=True)

    if( len(logFolder) != 0 ):
        errorFile = logFolder + 'errors.txt'

    genericErrorInfo(errorFile)

def workingFolder():
    return dirname(abspath(__file__)) + '/'

def getMementoRSSFeed(uri):

    if( len(uri) == 0 ):
        return '', {}

    rssMemento = archiveNowProxy(uri)
    id_rssMemento = ''
    rssFeed = {}
    
    indx = rssMemento.rfind('/http')
    if( indx != -1 ):
        id_rssMemento = rssMemento[:indx] + 'id_' + rssMemento[indx:]

    if( len(id_rssMemento) != 0 ):
        try:
            rssFeed = feedparser.parse(id_rssMemento)
        except:
            localErrorHandler()

    return id_rssMemento, rssFeed

def fetchLinksFromFeeds(uri, countOfLinksToGet=1, archiveRSSFlag=True):

    '''
        For news sources with rss links, get countOfLinksToGet links from uri

        param uri: rss link for source to dereference
        param countOfLinksToGet: the number of news links to extract for uri
    '''

    print('\tfetchLinksFromFeeds(), countOfLinksToGet:', countOfLinksToGet)
    
    uri = expandUrl(uri)
    uri = uri.strip()
    if( len(uri) == 0 ):
        return [], {}

    print('\t\turi:', uri)

    '''
        websites format:
        [
            {
                link: val,
                title: val,
                published: val
            },
        ]
    
    '''

    links = []
    verbose = False

    #attempt to process memento of rss - start
    if( archiveRSSFlag ):
        id_rssMemento, rssFeed = getMementoRSSFeed(uri)
    else:
        print('\t\tarchiveRSSFlag False')
        id_rssMemento = ''
        rssFeed = {}
    #attempt to process memento of rss - end

    if( len(rssFeed) == 0 ):
        print('\t\trss: use uri-r')
        #here means that for some reason it was not possible to process rss memento, so use live version
        try:
            rssFeed = feedparser.parse(uri)
        except:
            localErrorHandler()
    else:
        print('\t\trss: use uri-m:', id_rssMemento)


    for i in range(len(rssFeed.entries)):
        entry = rssFeed.entries[i]

        try:
            tempDict = {}

            if( 'link' not in entry ):
                continue

            tempDict['title'] = ''
            tempDict['published'] = ''
            tempDict['link'] = expandUrl(entry.link)    
            tempDict['rss-uri-m'] = id_rssMemento
            
            if( 'title' in entry ):
                tempDict['title'] =  entry.title
                if( verbose ):
                    print('\ttitle:', entry.title)

            if( 'published' in entry ):
                tempDict['published'] = entry.published
                if( verbose ):
                    print('\tpublished:', entry.published)
                    print('\tlink:', tempDict['link'])
                    print()

            links.append(tempDict)
        except:
            localErrorHandler()

        if( i+1 == countOfLinksToGet ):
            break

    return links, rssFeed

def getSourcesFromRSS(rssLinks, maxLinksToExtractPerSource=1, archiveRSSFlag=True):

    if( len(rssLinks) == 0 or maxLinksToExtractPerSource < 1 ):
        return {}, {}

    dedupDict = {}
    '''
        sourcesDict format:
        {
            domain_x: {link: link, ...},
            domain_y-0: {link: link, ...},
            domain_y-1: {link: link, ...}
        }
    '''
    sourcesDict = {}
    sourcesCountDict = {}
    sourcesToRename = {}
    domainRSSFeedsDict = {}
    throttle = 0
    for rssDict in rssLinks:

        if( throttle > 0 and archiveRSSFlag ):
            print('\n\tgetSourcesFromRSS(): throttle IA, sleep:', throttle)
            time.sleep(throttle)

        prevNow = datetime.now()        
        links, rssFeed = fetchLinksFromFeeds(rssDict['rss'].strip(), maxLinksToExtractPerSource, archiveRSSFlag=archiveRSSFlag)

        
        for uriDict in links:
            
            uriDict['link'] = uriDict['link'].strip()
            domain = getDomain(uriDict['link'], includeSubdomain=True)
            if( len(domain) == 0 ):
                continue

            uriDedupKey = getDedupKeyForURI( uriDict['link'] )
            if( uriDedupKey in dedupDict ):
                continue

            dedupDict[uriDedupKey] = True

            domainRSSFeedsDict.setdefault(domain, rssFeed)
            sourcesCountDict.setdefault(domain, -1)
            sourcesCountDict[domain] += 1

            #sourcesCountDict[domain] is count of domain instances already seen
            domainOrDomainCountKey = ''
            if( sourcesCountDict[domain] == 0 ):
                domainOrDomainCountKey = domain
            else:
                domainOrDomainCountKey = domain + '-' + str(sourcesCountDict[domain])
                sourcesToRename[domain] = True

            tempDict = {}
            for key, value in uriDict.items():
                tempDict[key] = value

            #transfer custom properties from rss - start
            if( 'custom' in rssDict ):
                for key, value in rssDict['custom'].items():
                    if( isinstance(value, dict) ):
                        tempDict[key] = copy.deepcopy(value)
                    else:    
                        tempDict[key] = value
            #transfer custom properties from rss - end

            sourcesDict[ domainOrDomainCountKey ] = tempDict
            #sourcesDict[ domainOrDomainCountKey ] = {'link': uri, 'title': uriDict['title'], 'published': uriDict['published'], 'label': rssDict['label']}
        
        delta = datetime.now() - prevNow
        if( delta.seconds < 1 ):
            throttle = 1
    #rename first instance of source with multiple instance as source-0 - start
    for domain in sourcesToRename:
        domainLink = sourcesDict[domain]['link']
        sourcesDict[domain + '-0'] = sourcesDict.pop(domain)
    #rename first instance of source with multiple instance as source-0 - end

    return sourcesDict, domainRSSFeedsDict

def addDetailsToEntities(entities2dList):

    '''
        entities2dList example:
        [['Portsmouth', 'LOCATION'], ['Va.', 'LOCATION'], ['Mr. Boyd', 'PERSON'], ['United States', 'LOCATION'], ['Philip M. Stinson', 'PERSON'], ['Bowling Green State University', 'ORGANIZATION'], ['Ohio', 'LOCATION'], ['Justice Department', 'ORGANIZATION'], ['Centers for Disease Control', 'ORGANIZATION'], ['2005', 'DATE'], ['Dr. Stinson', 'PERSON'], ['Albuquerque', 'LOCATION'], ['James Boyd', 'PERSON'], ['Albuquerque Police Department', 'ORGANIZATION'], ['Associated Press', 'ORGANIZATION'], ['Department of Defense', 'ORGANIZATION'], ['Special Forces', 'ORGANIZATION'], ['Mr. Perez', 'PERSON'], ['Randi McGinn', 'PERSON'], ['New York Times', 'ORGANIZATION']]
    '''
    dedupDict = {}
    entitiesList = []

    for entityTuple in entities2dList:
        
        entity = entityTuple[0]
        entityClass = entityTuple[1]

        tempDict = {}
        tempDict['entity'] = entity
        tempDict['class'] = entityClass
        entitiesList.append(tempDict)

    return entitiesList

'''
    mimics getEntitiesFromText to get 2d array of token and token class, e.g.,
    for text = 'Alexandre Desplat' and token class = 'TITLE'
    [
        ['Alexandre', 'TITLE'], 
        ['Desplat', 'TITLE']
    }
'''
def getTokenLabelsForText(text, label):

    if( len(text) == 0 or len(label) == 0 ):
        return []

    labeledTokens = []
    text = text.split(' ')
    
    for tok in text:
        tok = tok.strip()
        
        if( len(tok) == 0 or isExclusivePunct(tok) == True or isStopword(tok) == True ):
            continue

        labeledTokens.append([tok, label])

    return labeledTokens

def parallelNER(inputDict):
    return { 'entities2dList': getEntitiesFromText(inputDict['textToLabel'], inputDict['id'] + '.txt'), 'id': inputDict['id'] }

def parallelNERNew(inputDict):
    
    #iso8601Date not used
    iso8601Date = parseStrDate( inputDict['published'] )
    if( iso8601Date is None ):
        iso8601Date = ''
    else:
        iso8601Date = iso8601Date.strftime('%Y-%m-%dT%H:%M:%S')


    return { 
        'entities2dList': nlpGetEntitiesFromText(inputDict['textToLabel'],
        host=args.nlp_server_host,
        labelLst=['PERSON', 'LOCATION', 'ORGANIZATION', 'MONEY', 'PERCENT', 'DATE', 'TIME'],
        params={'normalizedTimeNER': True}
    ), 'id': inputDict['id'] }

def setSourceDictDetails(sourceDict):

    sourceDict['title'] = ''
    sourceDict['text'] = ''
    sourceDict['favicon'] = ''
    sourceDict['entities'] = []
    if( 'node-details' not in sourceDict ):
        sourceDict['node-details'] = {}
    sourceDict['extraction-time'] = ''


def getEntitiesAndEnrichSources(sources, paramsDict):
    #NOTE getEntitiesAndEnrichSourcesSequential DUPLICATES FUNCTIONALITY FOR SIMPLICITY
    #NOTE getEntitiesAndEnrichSourcesSequential DUPLICATES FUNCTIONALITY FOR SIMPLICITY
    #NOTE getEntitiesAndEnrichSourcesSequential DUPLICATES FUNCTIONALITY FOR SIMPLICITY
    #NOTE getEntitiesAndEnrichSourcesSequential DUPLICATES FUNCTIONALITY FOR SIMPLICITY
    #NOTE getEntitiesAndEnrichSourcesSequential DUPLICATES FUNCTIONALITY FOR SIMPLICITY
    print('\ngetEntities()')

    #check/set defaults - start
    if( 'addTitleClass' not in paramsDict ):
        paramsDict['addTitleClass'] = False

    if( 'addTopKTermsFlag' not in paramsDict ):
        paramsDict['addTopKTermsFlag'] = 0

    if( 'derefSleep' not in paramsDict ):
        paramsDict['derefSleep'] = 0

    if( 'threadPoolCount' not in paramsDict ):
        paramsDict['threadPoolCount'] = 5

    if( 'debugFlag' not in paramsDict ):
        paramsDict['debugFlag'] = False

    if( 'cacheFlag' not in paramsDict ):
        paramsDict['cacheFlag'] = False
    #check/set defaults - end

    if( paramsDict['threadPoolCount'] == 0 ):
        return getEntitiesAndEnrichSourcesSequential(sources, paramsDict)


    print('\tthreadPoolCount:', paramsDict['threadPoolCount'])

    textColToLabel = []
    listOfEntities2dList = []

    count = 1
    total = len(sources)
    nerVersion = ''
    for source, sourceDict in sources.items():
        
        if( paramsDict['debugFlag'] and paramsDict['cacheFlag'] ):
            html = derefURICache( sourceDict['link'] )
        else:
            html = dereferenceURI( sourceDict['link'], paramsDict['derefSleep'] )
        
        
        #set defaults - start
        setSourceDictDetails(sourceDict)
        #set defaults - end

        print('\tsource:', source)
        print('\t', count, 'of', total)
        count += 1

        if( html == '' ):
            continue

        title = extractPageTitleFromHTML(html)
        text = clean_html(html)
        text = sanitizeText(text)
        favicon = extractFavIconFromHTML(html, sourceDict['link'])

        print('\thtml.len:', len(html))
        print('\ttext.len:', len(text))
        print()
        if( text == '' ):
            continue

        
        sourceDict['title'] = title
        sourceDict['text'] = text
        sourceDict['favicon'] = favicon
        
        textColToLabel.append({
            'textToLabel': text, 
            'id': source,
            'published': sourceDict['published']
        })
    
    try:
        workers = Pool(paramsDict['threadPoolCount'])
        serverOn = nlpIsServerOn(args.nlp_server_host)

        if( serverOn ):
            print('\tNER version: 3.8.0')
            listOfEntities2dList = workers.map(parallelNERNew, textColToLabel)
            nerVersion = '3.8.0'
        else:
            print('\tNER version: old')
            #use old ner version since new server was not able to be started
            listOfEntities2dList = workers.map(parallelNER, textColToLabel)
            nerVersion = 'old'

        workers.close()
        workers.join()
    except:
        localErrorHandler()
        return sources

    for entitiesDetailsDict in listOfEntities2dList:
        
        source = entitiesDetailsDict['id']
        sources[source]['entities'] = entitiesDetailsDict['entities2dList']
        
        if( paramsDict['addTitleClass'] ):
            sources[source]['entities'] += getTokenLabelsForText( sources[source]['title'], 'TITLE' )

        #add top addTopKTermsFlag terms - start
        if( paramsDict['addTopKTermsFlag'] > 0 ):
            topKTerms = getTopKTermsListFromText( sources[source]['text'], paramsDict['addTopKTermsFlag'] )

            allTerms = ''
            for termCountTup in topKTerms:
                if( len(termCountTup) != 0 ):
                    allTerms += termCountTup[0] + ' '

            sources[source]['entities'] += getTokenLabelsForText( allTerms, 'TOP'+str(paramsDict['addTopKTermsFlag'])+'TERM' )
        #add top addTopKTermsFlag terms - end

        #clear some fields
        sources[source]['extraction-time'] = datetime.now().isoformat()
        sources[source]['entities'] = addDetailsToEntities( sources[source]['entities'] )

    return sources, nerVersion

def derefURICache(uri):

    uriFilename = workingFolder() + 'html-cache/' + getURIHash(uri) + '.html'

    if( os.path.exists(uriFilename) ):
        return readTextFromFile(uriFilename)
    else:
        html = dereferenceURI( uri, 0 )
        writeTextToFile(uriFilename, html)
        return html

def getEntitiesAndEnrichSourcesSequential(sources, paramsDict):

    print('\ngetEntities Sequential():')

    #check/set defaults - start
    if( 'addTitleClass' not in paramsDict ):
        paramsDict['addTitleClass'] = False

    if( 'addTopKTermsFlag' not in paramsDict ):
        paramsDict['addTopKTermsFlag'] = 0

    if( 'derefSleep' not in paramsDict ):
        paramsDict['derefSleep'] = 0

    if( 'debugFlag' not in paramsDict ):
        paramsDict['debugFlag'] = False

    if( 'cacheFlag' not in paramsDict ):
        paramsDict['cacheFlag'] = False
    #check/set defaults - end

    for source, sourceDict in sources.items():
        
        if( paramsDict['debugFlag'] and paramsDict['cacheFlag']  ):
            html = derefURICache( sourceDict['link'] )
        else:
            html = dereferenceURI( sourceDict['link'], paramsDict['derefSleep'] )
        
        #set defaults - start
        setSourceDictDetails(sourceDict)
        #set defaults - end

        if( len(html) == 0 ):
            continue

        title = extractPageTitleFromHTML(html)
        text = clean_html(html)
        favicon = extractFavIconFromHTML( html, sourceDict['link'] )

        if( len(text) == 0 ):
            continue

        entities2dList = getEntitiesFromText(text)

        #print('\n\ttitle:', title)
        #print('\tlink:', sourceDict['link'])
        #print('\tlen:', len(text.split(' ')), '\n')

        if( paramsDict['addTitleClass'] ):
            entities2dList = entities2dList + getTokenLabelsForText(title, 'TITLE')

        #add top addTopKTermsFlag terms - start
        if( paramsDict['addTopKTermsFlag'] > 0 ):
            topKTerms = getTopKTermsListFromText(text, paramsDict['addTopKTermsFlag'])

            allTerms = ''
            for termCountTup in topKTerms:
                if( len(termCountTup) != 0 ):
                    allTerms += termCountTup[0] + ' '

            entities2dList = entities2dList + getTokenLabelsForText(allTerms, 'TOP'+str(paramsDict['addTopKTermsFlag'])+'TERM')
        #add top addTopKTermsFlag terms - end

        text = sanitizeText(text)
        sourceDict['text'] = text
        sourceDict['title'] = title
        sourceDict['favicon'] = favicon
        sourceDict['extraction-time'] = datetime.now().isoformat()
        sourceDict['entities'] = addDetailsToEntities(entities2dList)

    return sources

def runGraphStories(sources, minSim, maxIter, thresholds):

    print('\nrunGraphStories():')

    if( len(sources) == 0 ):
        print('\tsources empty, returning')
        return {}

    storiesGraph = {}
    storiesGraph['links'] = []
    storiesGraph['nodes'] = []
    storiesGraph['connected-comps'] = []
    
    for source, sourceDict in sources.items():
        
        tempDict = {}
        tempDict['id'] = source
        for detailKey, detailValue in sourceDict.items():
            tempDict[detailKey] = detailValue

        storiesGraph['nodes'].append(tempDict)
        
        '''
            print(source)
            for entity in sourceDict['entities']:
                print('\t', entity['entity'], entity['class'])
        '''

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
    #minSim; 1 means 100% match. opposite similarityThreshold
    graphStories = GraphStories(storiesGraph, minSim, maxIter, thresholds['graph-building-thresholds'])
    storiesGraph = graphStories.graphStories()
    return storiesGraph

def censorGraphStories(sources):

    if( len(sources) == 0 ):
        return {}

    if( 'config' in sources ):
        del sources['config']

    for i in range(0, len(sources['nodes'])):
        if( 'entities' in sources['nodes'][i] ):
            del sources['nodes'][i]['entities']

        if( 'text' in sources['nodes'][i] ):
            del sources['nodes'][i]['text']

    return sources

def recusiveSetDefault(defaultConfig, config, count=0, parents=[]):

    '''
        Responsible for transfering default key/values from defaultConfig to config when absent,
        by recursively checking if keys are present, and indexing with ancestor keys. E.g., the ancestor
        keys of thread-pool-count below is ['entity-parameters']['thread-pool-count']:
        
        entity-parameters 0
            add-title-class 1
            add-top-k-terms-flag 1
            thread-pool-count 1

        But this function collapses the key indexing as such: ['entity-parameters', 'thread-pool-count']:

        FROM:

        history-count 0
        sleep-seconds 0
        debug-flag 0
        censor-flag 0
        output-folder 0
        entity-parameters 0
            add-title-class 1
            add-top-k-terms-flag 1
            thread-pool-count 1
        graph-parameters 0
            graph-building-thresholds 1
                distance-metric 2
                jaccard-weight 2
                overlap-weight 2
            event-thresholds 1
                min-avg-degree 2
                min-unique-source-count 2
            max-iterations 1
            min-sim 0
        feed-parameters 0
            max-extract-links-count 1
            feeds 1

        TO:

        history-count 0 ['history-count']
        sleep-seconds 0 ['sleep-seconds']
        debug-flag 0 ['debug-flag']
        censor-flag 0 ['censor-flag']
        output-folder 0 ['output-folder']
        entity-parameters 0 ['entity-parameters']
            add-title-class 1 ['entity-parameters', 'add-title-class']
            add-top-k-terms-flag 1 ['entity-parameters', 'add-top-k-terms-flag']
            thread-pool-count 1 ['entity-parameters', 'thread-pool-count']
        graph-parameters 0 ['graph-parameters']
            graph-building-thresholds 1 ['graph-parameters', 'graph-building-thresholds']
                distance-metric 2 ['graph-parameters', 'graph-building-thresholds', 'distance-metric']
                jaccard-weight 2 ['graph-parameters', 'graph-building-thresholds', 'jaccard-weight']
                overlap-weight 2 ['graph-parameters', 'graph-building-thresholds', 'overlap-weight']
            event-thresholds 1 ['graph-parameters', 'event-thresholds']
                min-avg-degree 2 ['graph-parameters', 'event-thresholds', 'min-avg-degree']
                min-unique-source-count 2 ['graph-parameters', 'event-thresholds', 'min-unique-source-count']
            max-iterations 1 ['graph-parameters', 'max-iterations']
            sim-sim 0 ['graph-parameters', 'min-sim']
        feed-parameters 0 ['feed-parameters']
            max-extract-links-count 1 ['feed-parameters', 'max-extract-links-count']
            feeds 1 ['feed-parameters', 'feeds']
    '''
    if( len(defaultConfig) == 0 ):
        return

    tabs = '\t' * count 
    if( isinstance(defaultConfig, dict) ):
        for key, value in defaultConfig.items():

            if( count == 0 ):
                #reset and add since at level 0 there's no parent e.g, history-count
                parents = []
                parents.append(key)
            else:
                #here means a parent exists
                if( count < len(parents) ):
                    #here means a previous child at the same level has been added, so override, e.g, ['entity-parameters', 'add-title-class'] was added, so override with ['entity-parameters', 'add-top-k-terms-flag ']
                    parents[count] = key
                    
                    #here means that a from another parent at a higher level has been added, so remove since this child does not belong to the lineage: e.g, going from
                    #['graph-parameters', 'graph-building-thresholds', 'overlap-weight'] to ['graph-parameters', 'event-thresholds'], so remove everything after current child
                    if( parents[count] !=  parents[-1] ):
                        parents = parents[:count+1]
                else:
                    #here means child has not been added
                    parents.append(key)
            
            #feed shall not be copied
            if( parents[-1] != 'feeds' ):
                if( getFromDict(config, parents) is None ):
                    setInDict(config, parents, value)
                
                #print(tabs + key, count, parents)

                if( isinstance(value, dict) ):
                        recusiveSetDefault(value, config=config, count=count+1, parents=parents)
                elif( isinstance(value, list) ):
                    for entry in value:
                        recusiveSetDefault(entry, config=config, count=count+1, parents=parents)
    
    elif( isinstance(defaultConfig, list) ):
        for entry in defaultConfig:
            recusiveSetDefault(entry, config=config, count=count+1, parents=parents)

def addSkipEntities( sources, skipTheseEntities ):

    if( len(skipTheseEntities) == 0 ):
        return

    for source, sourceDict in sources.items():
        
        allEnts = sourceDict.pop('entities')
        sourceDict['entities'] = []
        sourceDict['other-entities'] = []

        for ent in allEnts:
            if( ent['class'] in skipTheseEntities ):
                sourceDict['other-entities'].append(ent)
            else:
                sourceDict['entities'].append(ent)

def genGraph(defaultConfig, config):
    
    
    print('\ngenGraph():')

    if( len(defaultConfig) == 0 or len(config) == 0 ):
        print('\texiting since defaultConfig or config empty')
        print('\tdefaultConfig.len\config.len:', len(defaultConfig), len(config))
        return

    recusiveSetDefault(defaultConfig, config)
    print('\tdebug-flag:', config['debug-flag'])

    thresholds = {}
    thresholds['graph-building-thresholds'] = config['graph-parameters']['graph-building-thresholds']
    thresholds['event-thresholds'] = config['graph-parameters']['event-thresholds']

    entityBuildingParams = {}
    entityBuildingParams['addTitleClass'] = config['entity-parameters']['add-title-class']
    entityBuildingParams['addTopKTermsFlag'] = config['entity-parameters']['add-top-k-terms-flag']
    entityBuildingParams['threadPoolCount'] = config['entity-parameters']['thread-pool-count']
    entityBuildingParams['debugFlag'] = config['debug-flag']
    entityBuildingParams['cacheFlag'] = config['cache-html-flag']

    print('\twould skip entities in clustering:', config['clust-skip-ent-classes'])

    sources, domainRSSFeedsDict = getSourcesFromRSS( config['feed-parameters']['feeds'], maxLinksToExtractPerSource=config['feed-parameters']['max-extract-links-count'] )    
    sources, nerVersion = getEntitiesAndEnrichSources(sources, entityBuildingParams)
    addSkipEntities( sources, config['clust-skip-ent-classes'] )
    sources = runGraphStories(sources, minSim=config['graph-parameters']['min-sim'], maxIter=config['graph-parameters']['max-iterations'], thresholds=thresholds)
    
    if( config['debug-flag'] ):
        importlib.reload(graphAnnotate)

    if( len(config['annotation']) != 0 ):
        sources = graphAnnotate.annotate( selector=config['annotation'], storiesGraph=sources, eventThresholds=thresholds['event-thresholds'] )

    sources['ner-version'] = nerVersion
    #config['rss-feeds'] = {}#domainRSSFeedsDict
    sources['timestamp'] = getISO8601Timestamp()

    #create accessible config - start
    configJsonStr = json.dumps(config)
    configHashname = getHashForText(configJsonStr)
    configFilename = f'{args.data_path}generic/config-versions/' + configHashname + '.json'
    
    if( os.path.exists(configFilename) == False ):
        config['timestamp'] = sources['timestamp']
        dumpJsonToFile( configFilename, config )

    sources['config'] = '/files/config/' + config['name'] + '/' + configHashname + '/'
    #create accessible config - start
    
    if( config['censor-flag'] ):
        sources = censorGraphStories(sources)

    settings = {    
        'debug-flag': config['debug-flag'],
        'timestamp': sources['timestamp'],
        'name': config['name'],
        'history-count': config['history-count']
    }
    
    writeGraph( settings, sources )

def writeGraph(settings, sources):

    print('\nwriteGraph()')

    try:
        outputPath = f'{args.data_path}graphs/' + settings['name'] + '/'
        if( settings['debug-flag'] ):
            dumpJsonToFile( outputPath + 'graph.json', sources )
            return

        defaultGraphIndexDict = {'refresh-seconds': 300}

        #create folders if not exist - start
        date = settings['timestamp'].split('T')[0].split('-')
        os.makedirs(outputPath + date[0] + '/' + date[1] + '/' + date[2] + '/', exist_ok=True)
        
        oneDayGraphFileName = '{}{}/{}/{}/graphs-'.format( outputPath, date[0], date[1], date[2] )
        oneDayGraphFileName += '{}-{}-{}.jsonl.gz'.format( date[0], date[1], date[2] )

        oneDayOffsetFileName = '{}{}/{}/{}/byte-offsets-'.format( outputPath, date[0], date[1], date[2] )
        oneDayOffsetFileName += '{}-{}-{}.txt'.format( date[0], date[1], date[2] )
        
        offset_outfile = open(oneDayOffsetFileName, 'a')
        with open(oneDayGraphFileName, 'ab') as outfile:
            sources = json.dumps(sources, ensure_ascii=False) + '\n'
            sources = sources.encode()
            
            #new - start
            start_offset = outfile.tell()
            compressed_sources = gzip.compress(sources)
            outfile.write(compressed_sources)
            end_offset = outfile.tell() - 1

            offset_outfile.write( '{}, {}, {}\n'.format(settings['timestamp'], start_offset, end_offset) )
            #new - end

        offset_outfile.close()
    except:
        localErrorHandler()

def getGraphMaxAvgDeg(graph):

    if( 'connected-comps' not in graph ):
        return -1

    maxAvgDegree = -1
    for conComp in graph['connected-comps']:
        
        if( conComp['avg-degree'] > maxAvgDegree ):
            maxAvgDegree = conComp['avg-degree']

    return maxAvgDegree

def getUpdateNextGraphIndex_obsolete(historyCount, graphIndexFilename):
    
    graphIndex = readTextFromFile( graphIndexFilename ).strip()
    
    if( len(graphIndex) == 0 ):
        graphIndex = -1
    else:
        graphIndex = int(graphIndex)

    graphIndex += 1
    if( graphIndex >= historyCount ):
        graphIndex = 0

    writeTextToFile( graphIndexFilename, str(graphIndex) )
    return str(graphIndex)

def sleepCountDown(seconds):
    for i in range(seconds, 0, -1):
        time.sleep(1)
        sys.stdout.write(str(i)+' ')
        sys.stdout.flush()
    print()

def recusiveGetAllKeys(myDict, count=0, parents=[]):

    if( len(myDict) == 0 ):
        return

    tabs = '\t' * count 
    if( isinstance(myDict, dict) ):
        for key, value in myDict.items():

            if( count == 0 ):
                parents = []
                parents.append(key)
            else:
                if( count < len(parents) ):
                    parents[count] = key
                    
                    if( parents[count] !=  parents[-1] ):
                        parents = parents[:count+1]
                else:
                    parents.append(key)

            print(tabs + key, count, parents)

            if( isinstance(value, dict) ):
                recusiveGetAllKeys(value, count+1, parents)
            elif( isinstance(value, list) ):
                for entry in value:
                    recusiveGetAllKeys(entry, count+1, parents)
    
    elif( isinstance(myDict, list) ):
        for entry in myDict:
            recusiveGetAllKeys(entry, count+1, parents)

def getGenericArgs():
    parser = argparse.ArgumentParser(formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=30), description='Generate storygraphs')
    
    parser.add_argument('--nlp-server-host', default='stanfordcorenlp', help='Stanford NLP server host')
    parser.add_argument('-p', '--data-path', default='/data/', help='Storage location (graphs, config, etc)')
    parser.add_argument('-l', '--stay-alive', action='store_true', help='Run continuously in infinite loop')
    
    return parser

if __name__ == "__main__":

    parser = getGenericArgs()
    args = parser.parse_args()
    
    args.data_path = args.data_path.strip()
    args.data_path = args.data_path if args.data_path.endswith('/') else args.data_path + '/'

    while( True ):

        allParameters = getConfigParameters( f'{args.data_path}generic/serviceClusterStories.config.json' )
        prevNow = datetime.now()
        
        for job in allParameters['jobs']:
            try:
                childConfigPath = f'{args.data_path}graph-cursors/' + job['config']
                print('\tchildConfigPath:', childConfigPath)

                childConfig = getConfigParameters( childConfigPath )
                globalConfig['graphName'] = childConfig['name']
                genGraph( allParameters['default-config'], childConfig )
            except:
                localErrorHandler()
    
        delta = datetime.now() - prevNow
        print('\tdelta seconds:', delta.seconds)

        if( args.stay_alive is not True ):
            break
        
        sleepSecondsRemaining = allParameters['default-config']['sleep-seconds'] - delta.seconds
        if( sleepSecondsRemaining > 0 ):
            print('\tsleep seconds:', sleepSecondsRemaining)
            sleepCountDown(sleepSecondsRemaining)
    