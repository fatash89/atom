from atom import Element
from atom.messages import Response
from threading import Thread
from time import sleep

class AtomBot:

    def __init__(self):
        self.pos = 2
        self.max_pos = 5
        self.atombot = "o"

    def move_left(self, steps):
        """
        Moves AtomBot in left for a number of steps.

        Args:
            steps: Number of steps to move.
        """
        steps = int(steps)
        if steps < 0 or steps > self.max_pos:
            return Response(err_code=1, err_str=f"Steps must be between 0 and {self.max_pos}")
        self.pos = max(0, self.pos - steps)
        return Response(data=f"Moved left {steps} steps.")

    def move_right(self, steps):
        """
        Moves AtomBot in right for a number of steps.

        Args:
            steps: Number of steps to move.
        """
        steps = int(steps)
        if steps < 0 or steps > self.max_pos:
            return Response(err_code=1, err_str=f"Steps must be between 0 and {self.max_pos}")
        self.pos = min(self.max_pos, self.pos + steps)
        return Response(data=f"Moved right {steps} steps.")

    def transform(self, _):
        """
        Transforms AtomBot!
        """
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
    element = Element("atombot")
    atombot = AtomBot()
    element.command_add("move_left", atombot.move_left, timeout=50)
    element.command_add("move_right", atombot.move_right, timeout=50)
    element.command_add("transform", atombot.transform, timeout=50)

    thread = Thread(target=element.command_loop, daemon=True)
    thread.start()

    while True:
        element.entry_write("pos", {"data": atombot.pos}, maxlen=10)
        element.entry_write("pos_map", {"data": atombot.get_pos_map()}, maxlen=10)
        sleep(0.01)
