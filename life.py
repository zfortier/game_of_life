#!/usr/bin/env python3
# pylint: disable=C0114
import sys
import os
import curses
import pickle
import time

# pylint: disable=W0105
"""
A fully featured implementation of Conway's Game of Life for *NIX terminal. It
has no restrictions on board size, and is capable of automatically expanding
and contracting the board dimensions between generations to display the full
cellular universe without maintaining unused containers for empty rows.

The board is based on the builtin `dict` class. The board state is loaded from
files that are serialized using `pickle`. The actual data is not the LifeBoard
object itself, but the underlying dictionary data (the LifeBoard object is
rebuilt from the file. See the docstring under the LifeBoard class).
"""

LIVE_CELL_GLYPH = "*"
DEAD_CELL_GLYPH = " "
BOARD_START_SIZE = 100 # square board
BOARD_MAX_SIZE = 1000 # cells die when they reach the edge
SAVE_FF_CHOICES = False
MAX_SIZE = float("inf")
EDGE_BUF_SIZE = 2


class LifeBoard(dict):
    """
    LifeBoard is a custom object that inherits from the `dict` builtin. It uses
    a dictionary of sets to store the grid. The dictionary keys are row numbers
    on the Life grid, and the set members are the live columns within that row.
    This makes element lookup extremely efficient as keying into a dictionary
    and seeking an element from a set are both O(1) operations.

    The number of rows is given as variable `height`, with the table growing
    from row 0 downward, so that the maximum index in the dictionary will be
    `height - 1` with all intermediate row numbers included as keys (even if
    they are empty). The board is automatically resized, allowing live cells to
    multiply freely. An empty buffer region is maintained on both the top and
    bottom of the grid (no buffer is needed on the left/right sides).
    """

    live_cell = f" {LIVE_CELL_GLYPH}"
    dead_cell = f" {DEAD_CELL_GLYPH}"

    def __init__(self, start_height=None, source_file=None):
        """
        creates a new board by constructing the supporting structure in the
        superclass. Either `start_height` or `source_file` must be provided.
        """
        self.curr_board = None
        self.height = (start_height if start_height else 0)
        self.min_max = {"max": int(sys.float_info.max),
                        "min": -1 * int(sys.float_info.max)}
        if source_file and os.path.isfile(source_file):
            with open(source_file, 'rb') as fin:
                super().__init__(pickle.load(fin))
        else:
            super().__init__({n: set() for n in range(start_height
                                                      if start_height else 0)})
        self.height = 0
        for row in self.values():
            self.height += 1
            for cell in row:
                if cell < self.min_max["max"]:
                    self.min_max["max"] = cell
                if cell > self.min_max["min"]:
                    self.min_max["min"] = cell


    def __repr__(self):
        """
        returns a copy of the superclass to allow a more portable save file.
        """
        return str(dict(self))


    def __str__(self):
        ret_val = "\n"
        for row_num in range(self.height):
            for col_num in range(self.min_max["max"] - EDGE_BUF_SIZE,
                                 self.min_max["min"] + EDGE_BUF_SIZE):
                if col_num in self[row_num]:
                    ret_val += self.live_cell
                else:
                    ret_val += self.dead_cell
            ret_val += "\n"
        ret_val += f"\nheight: {self.height}, " \
              + f"width: {self.min_max['min'] - self.min_max['max'] + 1}, " \
              + f"min_max: {self.min_max}"
        return ret_val


    def resize_board(self):
        """
        First expands the board as needed, then shrinks as needed.
        Automatically expand the board from the top and bottom so that there is
        always a buffer of empty rows on both sides.
        Prunes rows from the top and bottom of the board to maintain the right
        empty buffer size on each side.
        """
        # Expand first...
        while any(self[n] for n in range(EDGE_BUF_SIZE)):
            for row_num in range(self.height, 0, -1):
                self[row_num] = self[row_num - 1]
            self[0] = set()
            self.height += 1
        while any(self[self.height - n] for n in range(1, EDGE_BUF_SIZE + 1)):
            self[self.height] = set()
            self.height += 1
        # ...then shrink
        while not self[EDGE_BUF_SIZE]: # top 2 rows have no live cells
            self.pop(0)
            for row_num in range(1, self.height):
                self[row_num - 1] = self[row_num]
            self.height -= 1
        while not self[self.height - EDGE_BUF_SIZE + 1]:
            self.pop(self.height - 1)
            self.height -= 1


    def compute_next_generation(self):
        """
        Applies the rules of Life to the current board state to construct a
        list of deltas. Then applies the deltas to the board itself, advancing
        the state by 1 generation. Afterwards, the board is resized to
        """
        deltas = []
        for row_num in range(1, self.height - 1):
            for cell in range(self.min_max["max"] - 1,
                              self.min_max["min"] + 2):
                neighbor_ct = (((cell - 1) in self[row_num - 1])
                               + (cell in self[row_num - 1])
                               + ((cell + 1) in self[row_num - 1])
                               + ((cell - 1) in self[row_num])
                               + ((cell + 1) in self[row_num])
                               + ((cell - 1) in self[row_num + 1])
                               + (cell in self[row_num + 1])
                               + ((cell + 1) in self[row_num + 1]))
                if cell not in self[row_num] and neighbor_ct == 3:
                    deltas.append((row_num, cell, True))
                elif cell in self[row_num]:
                    if neighbor_ct not in (2, 3):
                        deltas.append((row_num, cell, False))
        for delta in deltas:
            try:
                if delta[2]:
                    self[delta[0]].add(delta[1])
                else:
                    self[delta[0]].remove(delta[1])
            except KeyError:
                print(f"value error: {delta}\n{self[delta[0]]}")
            if delta[0] < self.min_max["max"]:
                self.min_max["max"] = delta[0]
            if delta[1] > self.min_max["min"]:
                self.min_max["min"] = delta[1]
        self.resize_board()



def redraw_screen(screen, board=None, clear=False): #pylint: disable=C0116
    """
    clears and refreshes the screen, and redraws the board.
    """
    if clear:
        screen.clear()
    screen.refresh()
    if board:
        print(board)


def get_and_apply_user_settings(screen): # pylint: disable=C0116
    """
    Displays the user settings options, prompts the user to make a selection,
    reads the selection, and sets the associated property. Secondary inputs
    are obtained where needed.
    """
    redraw_screen(screen)
    print("\n1) Set board size\n2) Automatically apply Fast Forward settings")
    print("3) Enable board perimiter\n4) Return to Main Menu")
    choice = input("Choice: ")
    if not choice.isdigit():
        choice = '4'
    if choice.isdigit():
        choice = int(choice)
        if choice == 1:
            new_size = input("Enter new size: ")
            if new_size.isdigit():
                global BOARD_START_SIZE # pylint: disable=W0603
                BOARD_START_SIZE = int(new_size)
        if choice == 2:
            global SAVE_FF_CHOICES # pylint: disable=W0603
            SAVE_FF_CHOICES = True
        if choice == 3:
            max_size = input ("Enter the maximum board size: ")
            if max_size.isdigit():
                global MAX_SIZE # pylint: disable=W0603
                MAX_SIZE = int(max_size)


def menu(screen): # pylint: disable=C0116, R0912, R0915
    """
    This function controls the overall flow of the program. It displays the
    main menu when the program starts, and between evolutions of the simulator.
    Creates and manages the main board object.
    """
    curses.reset_shell_mode()
    if len(sys.argv) > 1:
        board = LifeBoard(source_file = sys.argv[1])
    else:
        board = LifeBoard(start_height = BOARD_START_SIZE)
        repeat = False
    while True: # pylint: disable=R1702
        choice = None
        print("\n1) load board\n2) display board\n3) Settings")
        print("4) Progress one generation & display result")
        print("5) fast-forward\n6) save board\n7) exit")
        choice = input("Choice: ")
        redraw_screen(screen)
        if not choice.isdigit() and repeat:
            choice = '3'
            repeat = False
            get_and_apply_user_settings(screen)
        if choice.isdigit():
            choice = int(choice)
            if choice == 1:
                redraw_screen(screen)
                f_name = input("Enter file name: ")
                if f_name and os.path.isfile(f_name):
                    board = LifeBoard(source_file = f_name)
                    redraw_screen(screen)
                else:
                    print("bad file name")
            elif choice == 2:
                if board:
                    redraw_screen(screen, board)
            elif choice == 3:
                redraw_screen(screen)
            elif choice == 4:
                board.compute_next_generation()
                redraw_screen(screen, board, True)
                repeat = True
            elif choice == 5:
                redraw_screen(screen, board)
                num_gens = input("How many generations? ")
                if num_gens and num_gens.isdigit():
                    num_gens = int(num_gens)
                    disp = input("Display intermediate boards (y/N): ").lower()
                    if disp == 'y':
                        nth = input("How often (every n-th generation, blank for never)? ")
                        nth = (int(nth) if nth and nth.isdigit() else -1)
                        delay = input("Display delay time (2s)? ")
                        delay = (int(delay) if delay.isdigit() else 2)
                    for gen in range(num_gens):
                        board.compute_next_generation()
                        if (disp == 'y' and ((gen % nth) == 0)
                                and gen != num_gens - 1):
                            redraw_screen(screen, board)
                            time.sleep(delay)
                    redraw_screen(screen, board)
                    time.sleep(delay)
            elif choice == 6:
                f_name = input("Enter file name: ")
                if f_name and not os.path.isfile(f_name):
                    with open(f_name, 'wb') as fout:
                        pickle.dump(repr(board), fout)
                elif f_name:
                    print("File Exists!")
                else:
                    print("bad file name")
            elif choice == 7:
                redraw_screen(screen)
                sys.exit()


if __name__ == "__main__":
    curses.wrapper(menu)
