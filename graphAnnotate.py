import networkx as nx

def newsEventAnnotate(annotationName, storiesGraph, eventThresholds):

	print('\nnewsEventAnnotate():')

	if( 'links' not in storiesGraph or 'nodes' not in storiesGraph ):
		return storiesGraph

	#reset state - start
	for i in range(0, len(storiesGraph['nodes'])):

		if( 'node-details' not in storiesGraph['nodes'][i] ):
			storiesGraph['nodes'][i]['node-details'] = {}

		if( 'annotation' not in storiesGraph['nodes'][i]['node-details'] ):
			storiesGraph['nodes'][i]['node-details']['annotation'] = annotationName
			
		storiesGraph['nodes'][i]['node-details']['connected-comp-type'] = ''
	#reset state - end	

	if( len(storiesGraph['links']) == 0 ):
		return storiesGraph

	annotationName = storiesGraph['nodes'][0]['node-details']['annotation']

	G = nx.Graph()
	for edge in storiesGraph['links']:
		G.add_edge(edge['source'], edge['target'])
	
	storiesGraph['connected-comps'] = []
	subgraphs = list(nx.connected_component_subgraphs(G))
	for subgraph in subgraphs:
		
		e = sum(subgraph.degree().values())
		v = subgraph.number_of_nodes()
		avgDegree = e/float(v)
		nodes = subgraph.nodes()
		uniqueSourceCountDict = {}

		for storyIndex in nodes:
			source = storiesGraph['nodes'][storyIndex]['id'].split('-')[0]
			uniqueSourceCountDict[source] = True

		connectedCompType = {}
		connectedCompType['annotation'] = annotationName
		if( avgDegree >= eventThresholds['min-avg-degree'] and len(uniqueSourceCountDict) >= eventThresholds['min-unique-source-count'] ):
			connectedCompType['connected-comp-type'] = 'event'
			connectedCompType['color'] = 'green'
		else:
			connectedCompType['connected-comp-type'] = 'cluster'
			connectedCompType['color'] = 'red'

		connectedCompsDetails = {}
		connectedCompsDetails['nodes'] = nodes
		connectedCompsDetails['node-details'] = connectedCompType
		connectedCompsDetails['avg-degree'] = avgDegree
		connectedCompsDetails['density'] = nx.density(subgraph)
		connectedCompsDetails['unique-source-count'] = len(uniqueSourceCountDict)

		for storyIndex in nodes:
			if( 'color' not in storiesGraph['nodes'][storyIndex]['node-details'] ):
				storiesGraph['nodes'][storyIndex]['node-details']['color'] = connectedCompType['color']
			storiesGraph['nodes'][storyIndex]['node-details']['connected-comp-type'] = connectedCompType['connected-comp-type']

		storiesGraph['connected-comps'].append(connectedCompsDetails)


	return storiesGraph

def annotate(selector, storiesGraph, eventThresholds):
	
	if( selector == 'event-cluster' ):
		storiesGraph = newsEventAnnotate(selector, storiesGraph, eventThresholds)

	return storiesGraph