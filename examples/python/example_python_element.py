import time
from atom import Atom

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

	# Make our interface to Atom
	atom = Atom("example_element")

	# Register a few commands
	atom.add_command("hello_world", hello_world_handler)
	atom.add_command("foo_bar", foo_bar_handler)

	# In a loop, publish a monotonic increasing number on a stream
	i = 0
	while True:
		atom.entry_write("example_stream", {"data": i})
		time.sleep(0.1)
		i += 1
