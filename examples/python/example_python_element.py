import time
from skills.skill import Skill

def hello_world_handler(data):
	"""
	Example command handler
	"""
	print("hello world: Got Data {}".format(data))
	return "hello, world!"

def foo_bar_handler(data):
	"""
	Example command handler
	"""
	print("foobar: Got Data: {}".format(data))
	return "foobar"

if __name__ == '__main__':

	# Make our element
	element = Skill("example_element")

	# Add a few commands to the element
	element.add_command("hello_world", hello_world_handler)
	element.add_command("foo_bar", foo_bar_handler)

	# Now, in a loop, publish a monotonic increasing number on
	#	a stream
	i = 0
	while True:
		element.add_droplet("example_stream", {"data": i})
		time.sleep(0.1)
		i += 1
