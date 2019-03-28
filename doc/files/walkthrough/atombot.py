# atombot.py
from atom import Element
from atom.messages import Response
from threading import Thread
from time import sleep

class AtomBot:

    def __init__(self):
        # This defines atombot's current position
        self.pos = 2
        # We allow 5 different positions that atombot can move to
        self.max_pos = 5
        # An ascii representation of atombot!
        self.atombot = "o"

    def move_left(self, steps):
        """
        Command for moving AtomBot in left for a number of steps.

        Args:
            steps: Number of steps to move.
        """
        # Note that we are responsible for converting the data type from the sent command
        steps = int(steps)
        if steps < 0 or steps > self.max_pos:
            # If we encounter an error, we can send an error code and error string in the response of the command
            return Response(err_code=1, err_str=f"Steps must be between 0 and {self.max_pos}")
        self.pos = max(0, self.pos - steps)
        # If successful, we simply return a success string
        return Response(data=f"Moved left {steps} steps.")

    def move_right(self, steps):
        """
        Command for moving AtomBot in right for a number of steps.

        Args:
            steps: Number of steps to move.
        """
        # Note that we are responsible for converting the data type from the sent command
        steps = int(steps)
        if steps < 0 or steps > self.max_pos:
            # If we encounter an error, we can send an error code and error string in the response of the command
            return Response(err_code=1, err_str=f"Steps must be between 0 and {self.max_pos}")
        self.pos = min(self.max_pos, self.pos + steps)
        # If successful, we simply return a success string
        return Response(data=f"Moved right {steps} steps.")

    def transform(self, _):
        """
        Command for transforming AtomBot!
        """
        # Notice that we must have a single parameter to a command, even if we aren't using it.
        if self.atombot == "o":
            self.atombot = "O"
        else:
            self.atombot = "o"
        return Response(data=f"Transformed to {self.atombot}!")

    def get_pos_map(self):
        """
        Returns the current position of AtomBot as a visual.
        """
        pos_map = ["-"] * self.max_pos
        pos_map[self.pos] = self.atombot
        return " ".join(pos_map)



if __name__ == "__main__":
    # Create our element and call it "atombot"
    element = Element("atombot")

    # Instantiate our AtomBot class
    atombot = AtomBot()

    # This registers the relevant AtomBot methods as a command in the atom system
    # We set the timeout so the caller will know how long to wait for the command to execute
    element.command_add("move_left", atombot.move_left, timeout=50)
    element.command_add("move_right", atombot.move_right, timeout=50)
    element.command_add("transform", atombot.transform, timeout=50)

    # We create a thread and run the command loop which will constantly check for incoming commands from atom
    # We use a thread so we don't hang on the command_loop function because we will be performing other tasks
    thread = Thread(target=element.command_loop, daemon=True)
    thread.start()

    # Create an infinite loop that publishes the position of atombot to a stream as well as a visual of its position
    while True:
        # We write our position data and the visual of atombot's position to their respective streams
        # The maxlen parameter will determine how many entries atom stores
        element.entry_write("pos", {"data": atombot.pos}, maxlen=10)
        element.entry_write("pos_map", {"data": atombot.get_pos_map()}, maxlen=10)
        # Sleep so that we aren't consuming all of our CPU resources
        sleep(0.01)
