from collections import OrderedDict
import html2text
from bs4 import BeautifulSoup
import re
import math

text_maker = html2text.HTML2Text()
text_maker.body_width = 0 #disable random line-wrapping from html2text

def get_node_children(node):
	return OrderedDict(sorted(node.get('ideas', dict()).iteritems(), key=lambda t: float(t[0]))).values()

def remove_child(parent, node):
	children = parent.get('ideas', dict())
	for key, value in children.items():
		if value is node:
			children.pop(key)
	return

def is_node_a_leaf(node):
	return len(get_node_children(node)) == 0

def get_node_title(node):
	return node.get('title', '')

def set_node_title(node, title):
	node.update({'title': title})
	return

def is_mitigation(node):
	return is_node_a_leaf(node) and ( 'Mitigation: ' in get_node_title(node) )

def is_subtree(node):
	raw_description = get_raw_description(node)
	return 'SUBTREE::' in raw_description

def is_objective(node):
	raw_description = get_raw_description(node)
	return 'OBJECTIVE::' in raw_description

def is_riskpoint(node):
	raw_description = get_raw_description(node)
	return 'RISK_HERE::' in raw_description

def is_outofscope(node):
	raw_description = get_raw_description(node)
	return ( "out of scope".lower() in raw_description.lower() ) or ( 'OUT_OF_SCOPE::' in raw_description )

def is_collapsed(node):
	return node.get('attr', dict()).get('collapsed', False)

def is_all_children(node, predicate):
	for child in get_node_children(node):
		if not predicate(child):
		    return False
	return True

def is_attack_vector(node):
	if is_node_a_leaf(node):
	    return (not is_mitigation(node)) and (not is_objective(node))
	else:
	    return is_all_children(node, is_mitigation)

def is_objective(node):
	raw_description = get_raw_description(node)
	return 'OBJECTIVE::' in raw_description

def apply_each_node(root, fn):
	for child in get_node_children(root):
		apply_each_node(child, fn)
	fn(root)

	return

def apply_each_node_below_objectives(root, fn):
	objectives = list()
	def objectives_collector(node):
		if is_objective(node):
			objectives.append(node)
		return
	apply_each_node(root, objectives_collector)

	for objective in objectives:
		for child in get_node_children(objective):
			apply_each_node(child, fn)

	return

def do_each_once_with_deref(node, parent, fn, nodes_lookup):
	if node.get('done', False):
		return

	node.update({'inprogress': True})

	if is_node_a_reference(node):
		node_referent = get_node_referent(node, nodes_lookup)

		if not node_referent.get('inprogress', False):
			do_each_once_with_deref(node_referent, parent, fn, nodes_lookup)
	else:
		if not is_node_a_leaf(node):
			for child in get_node_children(node):
				do_each_once_with_deref(child, node, fn, nodes_lookup)

		if not node.get('done', False):
			node.update({'done': True})
			fn(node, parent)

	node.update({'inprogress': False})
	return

def clear_once_with_deref(node):
	for child in get_node_children(node):
		clear_once_with_deref(child)

	node.update({'inprogress': False})
	node.update({'done': False})
	return

def build_nodes_lookup(root):
	nodes_lookup = dict()

	def collect_all_nodes(node):
		node_title = node.get('title', '')

		if node_title.strip() == 'AND':
			return

		if node_title == '...':
			return

		if is_node_a_reference(node):
			return

		if nodes_lookup.get(node_title, None) is None:
			nodes_lookup.update({node_title: node})
		return

	apply_each_node(root, collect_all_nodes)
	return nodes_lookup

def detect_html(text):
	return bool(BeautifulSoup(text, "html.parser").find())

def get_raw_description(node):
	#prefer the mindmup 2.0 'note' to the 1.0 'attachment'
	description = node.get('attr', dict()).get('note', dict()).get('text', '')
	if description is '':
		description = node.get('attr', dict()).get('attachment', dict()).get('content', '')

	return description

def update_raw_description(node, new_description):
	#prefer the mindmup 2.0 'note' to the 1.0 'attachment'
	description = node.get('attr', dict()).get('note', dict()).get('text', '')
	if not description is '':
		node.get('attr').get('note').update({'text': new_description})
	else:
		node.get('attr', dict()).get('attachment', dict()).update({'content': new_description})

def get_unclean_description(node):
	global text_maker

	description = get_raw_description(node) + '\n'

	#TODO: convert special characters e.g. %lt => <
	if detect_html(description):
		description = text_maker.handle(description)

	return description

def get_description(node):
	description = get_unclean_description(node)

	#remove line breaks between '|' -- to preserve tables in 1.0 mindmups (that end up in multiple <div>)
	description = re.sub(r'\|\n+\|', '|\n|', description, re.M)

	#remove special tags (e.g. SUBTREE:: OBJECTIVE:: EVITA::)
	description = description.replace('SUBTREE::', '').replace('OBJECTIVE::','').replace('RISK_HERE::', '').replace('OUT_OF_SCOPE::','')

	description = re.sub(r'\nEVITA::.*\n', '\n\n', description, re.M)

	#remove trailing whitespace
	description = re.sub(r'\s+$', '\n', description, flags=re.M)

	#remove trailing newlines
	description = re.sub(r'\n+$', '', description)

	#remove leading newlines
	description = re.sub(r'^\n+', '', description)

	return description

def get_node_referent_title(node):
	title = node.get('title', '')

	if '(*)' in node.get('title'):
		wip_referent_title = title.replace('(*)','').strip()
	else:
		referent_coords = re.search(r'\((\d+\..*?)\)', title).groups()[0]
		wip_referent_title = "%s %s" % (referent_coords, re.sub(r'\(\d+\..*?\)', '', title).strip())
	return wip_referent_title

def get_node_reference_title(node):
	title = node.get('title','')
	parsed_title = re.match(r'(\d+\..*?)\s(.*?)$',title).groups()

	wip_reference_title = "%s (%s)" % (parsed_title[1], parsed_title[0])
	return wip_reference_title

def is_node_a_reference(node):
	title = node.get('title', '')

	return (not title.find('(*)') == -1) or (not re.search(r'\(\d+\..*?\)', title) is None)

def get_node_referent(node, nodes_lookup):
	node_referent_title = get_node_referent_title(node)
	node_referent = nodes_lookup.get(node_referent_title, None)

	if node_referent is None:
		print("ERROR missing node referent: %s" % node_referent_title)
		return node
	else:
		return node_referent

def is_node_weigthed(node):
	apt = get_node_apt(node)
	return (not apt is None) and (not math.isnan(apt)) and (not math.isinf(apt))


def update_node_apt(node, apt):
	if node.get('attr', None) is None:
		node.update({'attr': dict()})

	node.get('attr').update({'evita_apt': apt})
	return

def pos_infs_of_children(node):
	for child in get_node_children(node):
		if get_node_apt(child) == float('-inf'):
			update_node_apt(child, float('inf'))

def neg_infs_of_children(node):
	for child in get_node_children(node):
		if get_node_apt(child) == float('inf'):
			update_node_apt(child, float('-inf'))

def get_max_apt_of_children(node):
	child_maximum = float('-inf')

	for child in get_node_children(node):
		if is_mitigation(child) or is_outofscope(child):
			continue
		child_maximum = max(child_maximum, get_node_apt(child))
	
	return child_maximum

def get_min_apt_of_children(node):
	child_minimum = float('inf')

	for child in get_node_children(node):
		if is_mitigation(child) or is_outofscope(child):
		    continue
		child_minimum = min(child_minimum, get_node_apt(child))

	return child_minimum

def get_node_apt(node):
	return node.get('attr', dict()).get('evita_apt', None)

def apt_propagator(node):
	if (not is_attack_vector(node)) and (not is_mitigation(node)):
		if node.get('title', None) == 'AND':
			pos_infs_of_children(node)
			update_node_apt(node, get_min_apt_of_children(node))
		else:
			neg_infs_of_children(node)
			update_node_apt(node, get_max_apt_of_children(node))
	return

def do_propagate_apt_without_deref(node):
	apply_each_node_below_objectives(node, apt_propagator)
	return

def do_propagate_apt_with_deref(node, nodes_lookup):
	if is_node_weigthed(node):
		return

	update_node_apt(node, float('nan'))

	if is_node_a_reference(node):
		node_referent = get_node_referent(node, nodes_lookup)
		node_referent_title=get_node_title(node_referent)

		if (not get_node_apt(node_referent) is None) and (math.isnan(get_node_apt(node_referent))):
			#is referent in-progress? then we have a loop. update the reference node with the identity of the tree reduction operation and return
			update_node_apt(node, float('-inf'))
		else:
			#otherwise, descend through referent's children

			#do all on the referent and copy the node apt back
			do_propagate_apt_with_deref(node_referent, nodes_lookup)

			update_node_apt(node, get_node_apt(node_referent))
	else:
		for child in get_node_children(node):
			do_propagate_apt_with_deref(child, nodes_lookup)
		
		apt_propagator(node)
	return

def do_count_fixups_needed(root_node):
	count = 0
	def fixups_counter(node):
		if (not is_mitigation(node)) and math.isinf(get_node_apt(node)):
			count = count + 1
		return

	apply_each_node_below_objectives(root_node, fixups_counter)
	return count

def do_fixup_apt(root_node):
	fixups_len = do_count_fixups_needed(root_node)

	def fixer_upper(node):
		if (not is_mitigation(node)) and math.isinf(get_node_apt(node)):
			do_propagate_apt_without_deref(node)
		return

	while fixups_len > 0:
		apply_each_node_below_objectives(root_node, fixer_upper)

		fixups_len_this_time = do_count_fixups_needed(root_node)
		if fixups_len_this_time >= fixups_len:
			fixups_needed = list()
			def fixups_collector(node):
				if (not is_mitigation(node)) and math.isinf(get_node_apt(node)):
					fixups_needed.append(node)
				return
			apply_each_node_below_objectives(root_node, fixups_collector)
			raise ValueError("ERROR couldn't resolve remaining infs %s" % fixups_needed)
			break
		else:
			fixups_len = fixups_len_this_time
	return

# TODO function for clearing all propagated APTs

def propagate_all_the_apts(root_node, nodes_lookup):
	def propagtor_closure(node):
		do_propagate_apt_with_deref(node, nodes_lookup)
	apply_each_node_below_objectives(root_node, propagtor_closure)
	# fixup by doing propagation withough fixup on outstanding -infs
	do_fixup_apt(root_node)
	#propagate one last time for good measure
	do_propagate_apt_without_deref(root_node)
	return
