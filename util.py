import hashlib
import json
import os, sys
import re
import requests
import operator
import string
import time

from functools import reduce
from os.path import dirname, abspath

from boilerpipe.extract import Extractor
from bs4 import BeautifulSoup
from dateparser import parse as parseDateStr
from datetime import datetime
from subprocess import check_output
from tldextract import extract
from urllib.parse import urlparse

#html/url - start

def archiveNowProxy(uri, params=None):
	
	uri = uri.strip()
	if( len(uri) == 0 ):
		return ''

	if( params is None ):
		params = {}

	if( 'timeout' not in params ):
		params['timeout'] = 10

	try:
		uri = 'https://web.archive.org/save/' + uri
		headers = getCustomHeaderDict()
		
		# push into the archive
		r = requests.get(uri, timeout=params['timeout'], headers=headers, allow_redirects=True)
		r.raise_for_status()
		# extract the link to the archived copy 
		if (r == None):
			print('\narchiveNowProxy(): Error: No HTTP Location/Content-Location header is returned in the response')
			return ''
			
		if 'Location' in r.headers:
			return r.headers['Location']
		elif 'Content-Location' in r.headers:
			return 'https://web.archive.org' + r.headers['Content-Location']	
		else:
			for r2 in r.history:
				if 'Location' in r2.headers:
					return r2.headers['Location']
				if 'Content-Location' in r2.headers:
					return r2.headers['Content-Location']
	except Exception as e:
		print('Error: ' + str(e))
	except:
		genericErrorInfo()
	
	return ''

def clean_html(html, method='python-boilerpipe'):
	
	if( len(html) == 0 ):
		return ''

	#experience problem of parallelizing, maybe due to: https://stackoverflow.com/questions/8804830/python-multiprocessing-pickling-error
	if( method == 'python-boilerpipe' ):
		try:
			extractor = Extractor(extractor='ArticleExtractor', html=html)
			return extractor.getText()
		except:
			genericErrorInfo()
	elif( method == 'nltk' ):
		"""
		Copied from NLTK package.
		Remove HTML markup from the given string.

		:param html: the HTML string to be cleaned
		:type html: str
		:rtype: str
		"""

		# First we remove inline JavaScript/CSS:
		cleaned = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", "", html.strip())
		# Then we remove html comments. This has to be done before removing regular
		# tags since comments can contain '>' characters.
		cleaned = re.sub(r"(?s)<!--(.*?)-->[\n]?", "", cleaned)
		# Next we can remove the remaining tags:
		cleaned = re.sub(r"(?s)<.*?>", " ", cleaned)
		# Finally, we deal with whitespace
		cleaned = re.sub(r"&nbsp;", " ", cleaned)
		cleaned = re.sub(r"  ", " ", cleaned)
		cleaned = re.sub(r"  ", " ", cleaned)

		#my addition to remove blank lines
		cleaned = re.sub("\n\s*\n*", "\n", cleaned)

		return cleaned.strip()

	return ''

'''
	Note size limit set to 4MB
'''
def dereferenceURI(URI, maxSleepInSeconds=5, extraParams=None):
	
	URI = URI.strip()
	if( len(URI) == 0 ):
		return ''

	if( extraParams is None ):
		extraParams = {}
	
	htmlPage = ''
	try:
		
		if( maxSleepInSeconds > 0 ):
			print('\tderef.URI(), sleep:', maxSleepInSeconds)
			time.sleep(maxSleepInSeconds)

		extraParams.setdefault('sizeRestrict', 4000000)
		htmlPage = mimicBrowser(URI, extraParams=extraParams)
	except:
		genericErrorInfo()
	
	return htmlPage

def downloadSave(response, outfile):
	
	try:
		with open(outfile, 'wb') as dfile:
			for chunk in response.iter_content(chunk_size=1024): 
				# writing one chunk at a time to pdf file 
				if(chunk):
					dfile.write(chunk) 
	except:
		genericErrorInfo()

def extractFavIconFromHTML(html, sourceURL):
	sourceURL = sourceURL.strip()
	favicon = ''
	try:
		
		soup = BeautifulSoup(html, 'html.parser')
		links = soup.findAll('link')
		breakFlag = False

		for link in links:
			if( link.has_attr('rel') ):
				for rel in link['rel']:
					
					rel = rel.lower().strip()
					if( rel.find('icon') != -1 or rel.find('shortcut') != -1 ):
						favicon = link['href'].strip()
						breakFlag = True
						break

			if( breakFlag ):
				break

		if( len(favicon) != 0 and len(sourceURL) != 0 ):
			
			if( favicon.find('//') == 0 ):
				favicon = 'http:' + favicon
			elif( favicon[0] == '/' ):
				scheme, netloc, path, params, query, fragment = urlparse( sourceURL )
				favicon = scheme + '://' + netloc + favicon
	except:
		genericErrorInfo()

	return favicon

def extractPageTitleFromHTML(html):

	title = ''
	try:
		soup = BeautifulSoup(html, 'html.parser')
		title = soup.find('title')

		if( title is None ):
			title = ''
		else:
			title = title.text.strip()
	except:
		genericErrorInfo()

	return title

def expandUrl(url, secondTryFlag=True, timeoutInSeconds='10'):

	#print('\tgenericCommon.py - expandUrl():', url)
	#http://tmblr.co/ZPYSkm1jl_mGt, http://bit.ly/1OLMlIF
	timeoutInSeconds = str(timeoutInSeconds)
	'''
	Part A: Attempts to unshorten the uri until the last response returns a 200 or 
	Part B: returns the lasts good url if the last response is not a 200.
	'''
	url = url.strip()
	if( url == '' ):
		return ''
	
	try:
		#Part A: Attempts to unshorten the uri until the last response returns a 200 or 
		output = check_output(['curl', '-s', '-I', '-L', '-m', '10', '-c', 'cookie.txt', url])
		output = output.decode('utf-8')
		output = output.splitlines()
		
		longUrl = ''
		path = ''
		locations = []

		for line in output:
			line = line.strip()
			if( line == '' ):
				continue

			if( line.lower().startswith('location:') ):
				#location: is 9
				locations.append( line[9:].strip() )

		if( len(locations) != 0 ):
			#traverse location in reverse: account for redirects to path
			#locations example: ['http://www.arsenal.com']
			#locations example: ['http://www.arsenal.com', '/home#splash']
			for url in locations[::-1]:
				
				if( url.strip().lower().find('/') == 0 and len(path) == 0 ):
					#find path
					path = url

				if( url.strip().lower().find('http') == 0 and len(longUrl) == 0 ):
					#find url
					
					#ensure url doesn't end with / - start
					#if( url[-1] == '/' ):
					#	url = url[:-1]
					#ensure url doesn't end with / - end

					#ensure path begins with / - start
					if( len(path) != 0 ):
						if( path[0] != '/' ):
							path = '/' + path
					#ensure path begins with / - end

					longUrl = url + path

					#break since we are looking for the last long unshortened uri with/without a path redirect
					break
		else:
			longUrl = url


		return longUrl
	except Exception as e:
		#Part B: returns the lasts good url if the last response is not a 200.
		print('\terror url:', url)
		print(e)
		#genericErrorInfo()

		
		
		if( secondTryFlag ):
			print('\tsecond try')
			return expandUrlSecondTry(url)
		else:
			return url

def expandUrlSecondTry(url, curIter=0, maxIter=100):

	'''
	Attempt to get first good location. For defunct urls with previous past
	'''

	url = url.strip()
	if( len(url) == 0 ):
		return ''

	if( maxIter % 10 == 0 ):
		print('\t', maxIter, ' expandUrlSecondTry(): url - ', url)

	if( curIter>maxIter ):
		return url


	try:

		# when using find, use outputLowercase
		# when indexing, use output
		
		output = check_output(['curl', '-s', '-I', '-m', '10', url])
		output = output.decode('utf-8')
		
		outputLowercase = output.lower()
		indexOfLocation = outputLowercase.rfind('\nlocation:')

		if( indexOfLocation != -1 ):
			# indexOfLocation + 1: skip initial newline preceding location:
			indexOfNewLineAfterLocation = outputLowercase.find('\n', indexOfLocation + 1)
			redirectUrl = output[indexOfLocation:indexOfNewLineAfterLocation]
			redirectUrl = redirectUrl.split(' ')[1]

			return expandUrlSecondTry(redirectUrl, curIter+1, maxIter)
		else:
			return url

	except:
		print('\terror url:', url)
		genericErrorInfo()
	

	return url

def getDedupKeyForURI(uri):

	uri = uri.strip()
	if( len(uri) == 0 ):
		return ''

	exceptionDomains = ['www.youtube.com']

	try:
		scheme, netloc, path, params, query, fragment = urlparse( uri )
		
		netloc = netloc.strip()
		path = path.strip()
		optionalQuery = ''

		if( len(path) != 0 ):
			if( path[-1] != '/' ):
				path = path + '/'

		if( netloc in exceptionDomains ):
			optionalQuery = query.strip()

		netloc = netloc.replace(':80', '')
		return netloc + path + optionalQuery
	except:
		print('Error uri:', uri)
		genericErrorInfo()

	return ''

def getCustomHeaderDict():

	headers = {
		'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36',
		'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
		'Accept-Language': 'en-US,en;q=0.5',
		'Accept-Encoding': 'gzip, deflate',
		'Connnection': 'keep-alive',
		'Cache-Control':'max-age=0'	
		}

	return headers

def getDomain(url, includeSubdomain=False, excludeWWW=True):

	url = url.strip()
	if( len(url) == 0 ):
		return ''

	if( url.find('http') == -1  ):
		url = 'http://' + url

	domain = ''
	
	try:
		ext = extract(url)
		
		domain = ext.domain.strip()
		subdomain = ext.subdomain.strip()
		suffix = ext.suffix.strip()

		if( len(suffix) != 0 ):
			suffix = '.' + suffix 

		if( len(domain) != 0 ):
			domain = domain + suffix
		
		if( excludeWWW ):
			if( subdomain.find('www') == 0 ):
				if( len(subdomain) > 3 ):
					subdomain = subdomain[4:]
				else:
					subdomain = subdomain[3:]


		if( len(subdomain) != 0 ):
			subdomain = subdomain + '.'

		if( includeSubdomain ):
			domain = subdomain + domain
	except:
		genericErrorInfo()
		return ''

	return domain

def getURIHash(uri):
	return getStrHash(uri)

def getHashForText(text):
	hash_object = hashlib.md5( text.encode() )
	return hash_object.hexdigest()

def isSizeLimitExceed(responseHeaders, sizeRestrict):

	if( 'Content-Length' in responseHeaders ):
		if( int(responseHeaders['Content-Length']) > sizeRestrict ):
			return True

	return False

def mimicBrowser(uri, getRequestFlag=True, extraParams=None):
	
	uri = uri.strip()
	if( len(uri) == 0 ):
		return ''

	if( extraParams is None ):
		extraParams = {}

	extraParams.setdefault('timeout', 10)
	extraParams.setdefault('sizeRestrict', -1)
	extraParams.setdefault('headers', getCustomHeaderDict())
	extraParams.setdefault('addResponseHeader', False)


	try:
		response = ''
		reponseText = ''
		if( getRequestFlag is True ):

			if( 'saveFilePath' in extraParams ):
				response = requests.get(uri, headers=extraParams['headers'], timeout=extraParams['timeout'], stream=True)#, verify=False
			else:
				response = requests.get(uri, headers=extraParams['headers'], timeout=extraParams['timeout'])#, verify=False
			
			if( extraParams['sizeRestrict'] != -1 ):
				if( isSizeLimitExceed(response.headers, extraParams['sizeRestrict']) ):
					return 'Error: Exceeded size restriction: ' + str(extraParams['sizeRestrict'])

			
			if( 'saveFilePath' in extraParams ):
				downloadSave(response, extraParams['saveFilePath'])
			else:
				reponseText = response.text

			if( extraParams['addResponseHeader'] ):
				return	{'responseHeader': response.headers, 'text': reponseText}

			return reponseText
		else:
			response = requests.head(uri, headers=extraParams['headers'], timeout=extraParams['timeout'])#, verify=False
			response.headers['status-code'] = response.status_code
			return response.headers
	except:

		genericErrorInfo()
		print('\tquery is: ', uri)
		if( getRequestFlag == False ):
			return {}
	
	return ''


#html/url - end

#dict/json - start

def dumpJsonToFile(outfilename, dictToWrite, indentFlag=True, extraParams=None):

	if( extraParams is None ):
		extraParams = {}

	extraParams.setdefault('verbose', True)

	try:
		outfile = open(outfilename, 'w')
		
		if( indentFlag ):
			json.dump(dictToWrite, outfile, ensure_ascii=False, indent=4)#by default, ensure_ascii=True, and this will cause  all non-ASCII characters in the output are escaped with \uXXXX sequences, and the result is a str instance consisting of ASCII characters only. Since in python 3 all strings are unicode by default, forcing ascii is unecessary
		else:
			json.dump(dictToWrite, outfile, ensure_ascii=False)

		outfile.close()

		if( extraParams['verbose'] ):
			print('\twriteTextToFile(), wrote:', outfilename)
	except:
		if( extraParams['verbose'] ):
			print('\terror: outfilename:', outfilename)
		genericErrorInfo()

def getDictFromFile(filename):

	try:

		if( os.path.exists(filename) == False ):
			return {}

		return getDictFromJson( readTextFromFile(filename) )
	except:
		print('\tgetDictFromFile(): error filename', filename)
		genericErrorInfo()

	return {}

def getDictFromJson(jsonStr):

	try:
		return json.loads(jsonStr)
	except:
		genericErrorInfo()

	return {}

def getFromDict(dataDict, mapList):
	#credit: https://stackoverflow.com/a/14692747
	
	try:
		return reduce(operator.getitem, mapList, dataDict)
	except Exception as e:
		if( isinstance(e, KeyError) == False ):
			genericErrorInfo()
		return None

def setInDict(dataDict, mapList, value):
	#credit: https://stackoverflow.com/a/14692747
	try:
		res = getFromDict( dataDict, mapList[:-1] )
		
		if( res is not None ):
			res[mapList[-1]] = value
	except:
		genericErrorInfo()
#dict/json - end

#file - start

def getNowFilename():
	filename = str(datetime.now()).split('.')[0]
	return filename.replace(' ', 'T').replace(':', '-')

def readTextFromFile(infilename):

	text = ''

	try:
		with open(infilename, 'r') as infile:
			text = infile.read()
	except:
		print('\treadTextFromFile()error filename:', infilename)
		genericErrorInfo()
	

	return text

def workingFolder():
	return dirname(abspath(__file__)) + '/'

def writeTextToFile(outfilename, text, extraParams=None):
	
	if( extraParams is None ):
		extraParams = {}

	if( 'verbose' not in extraParams ):
		extraParams['verbose'] = True

	try:
		with open(outfilename, 'w') as outfile:
			outfile.write(text)
		
		if( extraParams['verbose'] ):
			print('\twriteTextToFile(), wrote:', outfilename)
	except:
		genericErrorInfo()
#file - end


#text - start

def getEntitiesFromText(plaintext, outfilename='tempNERTextToTag.txt'):
	#print('\ngetEntitiesFromText::getEntities() - start')

	if( len(plaintext) == 0 ):
		return []

	filePathToTag = './NER-TEXT/'
	try:
		os.makedirs(filePathToTag, exist_ok=True)
		filePathToTag += outfilename

		outfile = open(filePathToTag, 'w')
		outfile.write(plaintext)
		outfile.close()
	except:
		genericErrorInfo()
		return []
	
	entities = []
	try:
		#tagedText = check_output([workingFolder() + 'runJavaNER.sh'])
		tagedText = check_output(['java', '-mx500m', '-cp', workingFolder() + 'stanford-ner-3.4.jar', 'edu.stanford.nlp.ie.crf.CRFClassifier', '-loadClassifier', workingFolder() + 'english.muc.7class.distsim.crf.ser.gz', '-textFile', filePathToTag, '-outputFormat', 'inlineXML', '2>', '/dev/null'])
		tagedText = str(tagedText)

		INLINEXML_EPATTERN  = re.compile(r'<([A-Z]+?)>(.+?)</\1>')
		
		dedupDict = {}
		for match in INLINEXML_EPATTERN.finditer(tagedText):
			#print(match.group(0))
			#match.group(2) is entity
			#match.group(1) is class

			if( match.group(2) not in dedupDict ):
				entityAndClass = [match.group(2), match.group(1)]
				entities.append(entityAndClass)
				dedupDict[match.group(2)] = False

		#dict which separates classes of entities into different arrays - start
		#entities = (match.groups() for match in INLINEXML_EPATTERN.finditer(tagedText))
		#entities = dict((first, list(map(itemgetter(1), second))) for (first, second) in groupby(sorted(entities, key=itemgetter(0)), key=itemgetter(0)))
		#for entityClass, entityClassList in entities.items():
			#entities[entityClass] = list(set(entityClassList))
		#dict which separates classes of entities into different arrays - end

		#remove temp file - start
		check_output(['rm', filePathToTag])
		#remove temp file - end

	except:
		genericErrorInfo()

	#print('\ngetEntitiesFromText::getEntities() - end')
	return entities

def getStopwordsDict():

	stopwordsDict = {
		"a": True,
		"about": True,
		"above": True,
		"across": True,
		"after": True,
		"afterwards": True,
		"again": True,
		"against": True,
		"all": True,
		"almost": True,
		"alone": True,
		"along": True,
		"already": True,
		"also": True,
		"although": True,
		"always": True,
		"am": True,
		"among": True,
		"amongst": True,
		"amoungst": True,
		"amount": True,
		"an": True,
		"and": True,
		"another": True,
		"any": True,
		"anyhow": True,
		"anyone": True,
		"anything": True,
		"anyway": True,
		"anywhere": True,
		"are": True,
		"around": True,
		"as": True,
		"at": True,
		"back": True,
		"be": True,
		"became": True,
		"because": True,
		"become": True,
		"becomes": True,
		"becoming": True,
		"been": True,
		"before": True,
		"beforehand": True,
		"behind": True,
		"being": True,
		"below": True,
		"beside": True,
		"besides": True,
		"between": True,
		"beyond": True,
		"both": True,
		"but": True,
		"by": True,
		"can": True,
		"can\'t": True,
		"cannot": True,
		"cant": True,
		"co": True,
		"could not": True,
		"could": True,
		"couldn\'t": True,
		"couldnt": True,
		"de": True,
		"describe": True,
		"detail": True,
		"did": True,
		"do": True,
		"does": True,
		"doing": True,
		"done": True,
		"due": True,
		"during": True,
		"e.g": True,
		"e.g.": True,
		"e.g.,": True,
		"each": True,
		"eg": True,
		"either": True,
		"else": True,
		"elsewhere": True,
		"enough": True,
		"etc": True,
		"etc.": True,
		"even though": True,
		"ever": True,
		"every": True,
		"everyone": True,
		"everything": True,
		"everywhere": True,
		"except": True,
		"for": True,
		"former": True,
		"formerly": True,
		"from": True,
		"further": True,
		"get": True,
		"go": True,
		"had": True,
		"has not": True,
		"has": True,
		"hasn\'t": True,
		"hasnt": True,
		"have": True,
		"having": True,
		"he": True,
		"hence": True,
		"her": True,
		"here": True,
		"hereafter": True,
		"hereby": True,
		"herein": True,
		"hereupon": True,
		"hers": True,
		"herself": True,
		"him": True,
		"himself": True,
		"his": True,
		"how": True,
		"however": True,
		"i": True,
		"ie": True,
		"i.e": True,
		"i.e.": True,
		"if": True,
		"in": True,
		"inc": True,
		"inc.": True,
		"indeed": True,
		"into": True,
		"is": True,
		"it": True,
		"its": True,
		"it's": True,
		"itself": True,
		"just": True,
		"keep": True,
		"latter": True,
		"latterly": True,
		"less": True,
		"made": True,
		"make": True,
		"may": True,
		"me": True,
		"meanwhile": True,
		"might": True,
		"mine": True,
		"more": True,
		"moreover": True,
		"most": True,
		"mostly": True,
		"move": True,
		"must": True,
		"my": True,
		"myself": True,
		"namely": True,
		"neither": True,
		"never": True,
		"nevertheless": True,
		"next": True,
		"no": True,
		"nobody": True,
		"none": True,
		"noone": True,
		"nor": True,
		"not": True,
		"nothing": True,
		"now": True,
		"nowhere": True,
		"of": True,
		"off": True,
		"often": True,
		"on": True,
		"once": True,
		"one": True,
		"only": True,
		"onto": True,
		"or": True,
		"other": True,
		"others": True,
		"otherwise": True,
		"our": True,
		"ours": True,
		"ourselves": True,
		"out": True,
		"over": True,
		"own": True,
		"part": True,
		"per": True,
		"perhaps": True,
		"please": True,
		"put": True,
		"rather": True,
		"re": True,
		"same": True,
		"see": True,
		"seem": True,
		"seemed": True,
		"seeming": True,
		"seems": True,
		"several": True,
		"she": True,
		"should": True,
		"show": True,
		"side": True,
		"since": True,
		"sincere": True,
		"so": True,
		"some": True,
		"somehow": True,
		"someone": True,
		"something": True,
		"sometime": True,
		"sometimes": True,
		"somewhere": True,
		"still": True,
		"such": True,
		"take": True,
		"than": True,
		"that": True,
		"the": True,
		"their": True,
		"theirs": True,
		"them": True,
		"themselves": True,
		"then": True,
		"thence": True,
		"there": True,
		"thereafter": True,
		"thereby": True,
		"therefore": True,
		"therein": True,
		"thereupon": True,
		"these": True,
		"they": True,
		"this": True,
		"those": True,
		"though": True,
		"through": True,
		"throughout": True,
		"thru": True,
		"thus": True,
		"to": True,
		"together": True,
		"too": True,
		"toward": True,
		"towards": True,
		"un": True,
		"until": True,
		"upon": True,
		"us": True,
		"very": True,
		"via": True,
		"was": True,
		"we": True,
		"well": True,
		"were": True,
		"what": True,
		"whatever": True,
		"when": True,
		"whence": True,
		"whenever": True,
		"where": True,
		"whereafter": True,
		"whereas": True,
		"whereby": True,
		"wherein": True,
		"whereupon": True,
		"wherever": True,
		"whether": True,
		"which": True,
		"while": True,
		"whither": True,
		"who": True,
		"whoever": True,
		"whole": True,
		"whom": True,
		"whose": True,
		"why": True,
		"will": True,
		"with": True,
		"within": True,
		"without": True,
		"would": True,
		"yet": True,
		"you": True,
		"your": True,
		"yours": True,
		"yourself": True,
		"yourselves": True
	}
	
	return stopwordsDict

def getStrHash(txt):

	txt = txt.strip()
	if( txt == '' ):
		return ''

	hash_object = hashlib.md5(txt.encode())
	return hash_object.hexdigest()

def getTopKTermsListFromText(text, k, minusStopwords=True):

	if( len(text) == 0 ):
		return []

	stopWordsDict = {}
	if( minusStopwords ):
		stopWordsDict = getStopwordsDict()

	topKTermDict = {}
	topKTermsList = []
	text = text.split(' ')

	for term in text:
		term = term.strip().lower()
		
		if( len(term) == 0 or term in stopWordsDict or isExclusivePunct(term) == True ):
			continue

		topKTermDict.setdefault(term, 0)
		topKTermDict[term] += 1

	sortedKeys = sorted( topKTermDict, key=lambda freq:topKTermDict[freq], reverse=True )

	if( k > len(sortedKeys) ):
		k = len(sortedKeys)

	for i in range(k):
		key = sortedKeys[i]
		topKTermsList.append((key, topKTermDict[key]))

	return topKTermsList


def isExclusivePunct(text):

	text = text.strip()
	for char in text:
		if char not in string.punctuation:
			return False

	return True

def isStopword(term):

	stopWordsDict = getStopwordsDict()
	if( term.strip().lower() in stopWordsDict ):
		return True
	else:
		return False

#iso8601Date: YYYY-MM-DDTHH:MM:SS
def nlpGetEntitiesFromText(text, host='localhost', iso8601Date='', labelLst=['PERSON','LOCATION','ORGANIZATION','DATE','MONEY','PERCENT','TIME'], params=None):

	if( text == '' ):
		return []

	if( params is None ):
		params = {}

	iso8601Date = iso8601Date.strip()

	#set default params - start
	params.setdefault('normalizedTimeNER', False)
	params.setdefault('listEntityContainer', True)#false means dict
	#set default params - start

	'''
	if( params['normalizedTimeNER'] ):
		if( iso8601Date == '' ):
			iso8601Date = getNowTime().replace(' ', 'T')
	else:
		iso8601Date = ''
	'''

	labelLst = set(labelLst)
	if( len(iso8601Date) != 0 ):
		iso8601Date = ',"date":"' + iso8601Date + '"'

	request = host + ':9000/?properties={"annotators":"entitymentions","outputFormat":"json"' + iso8601Date + '}'
	entities = []
	dedupSet = set()

	try:
		output = check_output(['wget', '-q', '-O', '-', '--post-data', text, request])
		parsed = json.loads(output.decode('utf-8'))
		#dumpJsonToFile( 'ner_output.json', parsed )#for debugging 

		if( 'sentences' not in parsed ):
			return []

		for sent in parsed['sentences']:
			
			if( 'entitymentions' not in sent ):
				continue

			for entity in sent['entitymentions']:

				#text is entity, ner is entity class
				dedupKey = entity['text'] + entity['ner']
				
				if( entity['text'] == '' or dedupKey in dedupSet or entity['ner'] not in labelLst ):
					continue
					
				#debug - start
				if( entity['ner'] == 'DATE' or entity['ner'] == 'TIME' ):
					if( params['normalizedTimeNER'] and 'normalizedNER' in entity ):
						#attempt to parse date
						parsedDate = genericParseDate( entity['normalizedNER'][:10] )
						if( parsedDate is not None ):
							entity['text'] = parsedDate.isoformat()[:19]
						else:
							entity['text'] = ''
				#debug - end
					
				if( params['listEntityContainer'] ):
					entities.append( [entity['text'], entity['ner']] )
				else:
					entities.append({
						'label': entity['ner'],
						'entity': entity['text']
					})
				
				dedupSet.add(dedupKey)
	except:
		genericErrorInfo()

	return entities

def sanitizeText(text):

	#UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83d' in position 3507: surrogates not allowed
	try:
		text.encode('utf-8')
	except UnicodeEncodeError as e:
		if e.reason == 'surrogates not allowed':	
			text = text.encode('utf-8', 'backslashreplace').decode('utf-8')
	except:
		text = ''

	return text
#text - end

def genericErrorInfo(errOutfileName='', errPrefix=''):
	exc_type, exc_obj, exc_tb = sys.exc_info()
	fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	errorMessage = fname + ', ' + str(exc_tb.tb_lineno)  + ', ' + str(sys.exc_info())
	print('\tERROR:', errorMessage)
	
	mode = 'w'
	if( os.path.exists(errOutfileName) ):
		mode = 'a'

	if( len(errPrefix) != 0 ):
		errPrefix = errPrefix + ': '

	errOutfileName = errOutfileName.strip()
	if( len(errOutfileName) != 0 ):
		outfile = open(errOutfileName, mode)
		outfile.write(getNowFilename() + '\n')
		outfile.write('\t' + errPrefix + errorMessage + '\n')
		outfile.close()

	return  sys.exc_info()

def getConfigParameters(configPathFilename, keyValue=''):

	keyValue = keyValue.strip()
	configPathFilename = configPathFilename.strip()
	if( len(configPathFilename) == 0 ):
		return ''

	returnValue = ''

	try:
		configFile = open(configPathFilename, 'r')
		config = configFile.read()
		configFile.close()

		jsonFile = json.loads(config)

		if( len(keyValue) == 0 ):
			returnValue = jsonFile
		else:
			returnValue = jsonFile[keyValue]
	except:
		genericErrorInfo()

	return returnValue

def getISO8601Timestamp():
	return datetime.utcnow().isoformat() + 'Z'

def genericParseDate(dateStr):
	from dateutil.parser import parse
	
	dateStr = dateStr.strip()
	if( len(dateStr) == 0 ):
		return None

	try:
		dateObj = parse(dateStr)
		return dateObj
	except:
		#genericErrorInfo()
		pass

	return None

def nlpIsServerOn(host='localhost', port='9000'):

	try:
		response = requests.head('http://' + host +':' + port + '/')
		
		if( response.status_code == 200 ):
			return True
		else:
			return False

	except:
		genericErrorInfo()

	return False

def nlpServerStartStop(msg='start'):

	if( msg == 'start' ):
		try:
			if( nlpIsServerOn() ):
				print('\tCoreNLP Server already on - no-op')
			else:
				print('\tStarting CoreNLP Server')
				#docker run --rm -d -p 9000:9000 --name stanfordcorenlp anwala/stanfordcorenlp
				check_output([
					'docker', 
					'run', 
					'--rm', 
					'-d', 
					'-p', 
					'9000:9000', 
					'--name',
					'stanfordcorenlp',
					'anwala/stanfordcorenlp'
				])

				#warm up server (preload libraries, so subsequent responses are quicker)
				nlpGetEntitiesFromText('A quick brown fox jumped over the lazy dog')
		except:
			genericErrorInfo()
	elif( msg == 'stop' ):
		try:
			check_output(['docker', 'rm', '-f', 'stanfordcorenlp'])
		except:
			genericErrorInfo()

def parseStrDate(strDate):

	try:
		return parseDateStr(strDate)
	except:
		genericErrorInfo()

	return None