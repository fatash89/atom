import time
from atom import Element

def hello_world_handler(data):
	"""
	Example command handler
	"""
	print(f"hello world: Got Data {data}")
	return "hello, world!"

def foo_bar_handler(data):
	"""
	Example command handler
	"""
	print(f"foobar: Got Data: {data}")
	return "foobar"

if __name__ == '__main__':

	# Instantiate our element
	element = Element("example_element")

	# Register a few commands
	element.command_add("hello_world", hello_world_handler)
	element.command_add("foo_bar", foo_bar_handler)

	# In a loop, publish a monotonic increasing number on a stream
	i = 0
	while True:
		element.entry_write("example_stream", {"data": i})
		time.sleep(0.1)
		i += 1
