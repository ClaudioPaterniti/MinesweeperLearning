import numpy as np

from typing import Union
from matplotlib.colors import Normalize as ColorNormalize
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from . import utils

class Game:
    def __init__(self,
            rows: int=16, columns: int=30, mines_n: Union[int, np.ndarray]=99, n: int=1):
        """
        :param mines_n: scalar or (n) - the number o mines in each game
        :param n: number of parallel games"""
        self.rng = np.random.default_rng()
        self.n = n
        self.rows = rows
        self.columns = columns
        self.size = rows*columns
        self.mines_n = np.full(n, mines_n) if np.isscalar(mines_n) else mines_n
        self.mines = utils.random_binary_matrices((n, rows, columns), mines_n)
        self.numbers = self._compute_number_cells() # grids with number of neighbor mines
        self.open_cells = np.zeros_like(self.mines)
        self.flags = np.zeros_like(self.mines)
        self.active_games = np.full(n, True)
        self.won = np.full(n, False)
        self.last_opened = np.zeros_like(self.mines)
        self.last_flagged = np.zeros_like(self.mines)

    def __getitem__(self, key):
        if isinstance(key, int):
            key = slice(key, key+1)
        g = Game(self.rows, self.columns, 1, 0)
        g.mines_n = self.mines_n[key]
        g.n = g.mines.shape[0]
        g.mines = self.mines[key]
        g.numbers = self.numbers[key]
        g.open_cells = self.open_cells[key]
        g.flags = self.flags[key]
        g.active_games = self.active_games[key]
        g.won = self.won[key]
        g.last_opened = self.last_opened[key]
        g.last_flagged = self.last_flagged[key]
        return g

    def _compute_number_cells(self): # compute the minesweeper numbers from the mine placements
        grids = np.zeros_like(self.mines)
        pad = np.pad(self.mines, [(0,0), (1,1), (1,1)])
        for i in range(-1,2):
            for j in range(-1,2):
                grids += pad[:, 1+i:self.rows+1+i , 1+j:self.columns+1+j] # the number of a cell is the sum of the nighbour mines
        grids[self.mines.astype(bool)] = -1
        return grids

    def reset(self):
        self.open_cells.fill(0)
        self.flags.fill(0)
        self.active_games.fill(True)
        self.won.fill(False)
        self.last_opened.fill(0)
        self.last_flagged.fill(0)

    def game_state(self, active_only: bool = False):
        """return the games with:
        0-8: open cell with corresponding minesweeper number,
        9: closed cell,
        10: flag"""
        state = self.numbers*self.open_cells + 9*(1-self.open_cells) + self.flags
        return state[self.active_games] if active_only else state

    def scores(self, final_only: bool = False):
        """return percentage of non-mine cells opened"""
        mask = np.logical_not(self.active_games) if final_only else np.full(self.n, True)
        to_open = self.size - self.mines_n
        return self.open_cells[mask].sum(axis=(1,2))/to_open

    def win_rate(self):
        return self.won.sum()/(1-self.active_games).sum()

    def move(self, to_open: np.ndarray = None, to_flag: np.ndarray = None) -> np.ndarray[bool]:
        """Open or flag cells if the moves do not lose.
        Returns bool array with shape (n) where false = losing move"""
        if to_open is None: to_open = np.zeros_like(self.mines[self.active_games])
        if to_flag is None: to_flag = np.zeros_like(to_open)
        self.last_opened[self.active_games] = to_open
        self.last_flagged[self.active_games] = to_flag
        correct_open = np.logical_not(np.any(self.mines[self.active_games]*to_open, axis=(1,2)))
        correct_flag = np.logical_not(np.any((1-self.mines[self.active_games])*to_flag, axis=(1,2)))
        correct = correct_open & correct_flag
        self.active_games[self.active_games] = correct
        self.open_cells[self.active_games] = np.bitwise_or(self.open_cells[self.active_games], to_open[correct])
        self.flags[self.active_games] = np.bitwise_or(self.flags[self.active_games], to_flag[correct])
        self.won = np.all(self.open_cells+self.mines, axis=(1,2))
        self.active_games[self.won] = False
        return correct

    def open_zero(self) -> np.ndarray[int]:
        """Open a 0. Use it at the start of the game only. (It opens a minimum cell if no zeroes)"""
        mins = (self.numbers + 10*self.mines).min(axis=(1,2)).reshape(self.n, 1 , 1)
        weighted_zeros = self.rng.random(self.mines.shape)*(self.numbers == mins)
        random_zero = weighted_zeros.reshape(self.n, -1).argmax(axis=1)
        h_ids = random_zero//self.columns
        w_ids = random_zero%self.columns
        to_open = np.zeros_like(self.mines)
        to_open[np.arange(self.n), h_ids, w_ids] = 1 # open one zero per game
        self.move(to_open)
        return to_open

    def random_open(self, rate: float) -> np.ndarray[int]:
        """Open random cells (cannot open mines). Use it at the start of the game only"""
        to_open = self.rng.random(self.mines.shape) < rate
        to_open = to_open*(1-self.mines) # do not open mines
        self.move(to_open)
        return to_open

    def random_flags(self, rate: float) -> np.ndarray[int]:
        """Flag random mines. Use it at the start of the game only"""
        to_flag = self.rng.random(self.mines.shape) < rate
        to_flag = to_flag*self.mines # only flag mines
        self.move(to_flag=to_flag)
        return to_flag

    def losing_moves(self) -> np.ndarray:
        """return (n,h,w) binary array of wrong openings (-1) or flags (+1) in the last actions"""
        return self.last_flagged*(1-self.mines) - self.last_opened*self.mines

    def pyplot_game(self,
            idx: int = 0, full_grid: bool = False, highlighted: Union[str, np.ndarray] = None,
            **plot_kwargs) -> Axes:
        """plot game state
        :param idx: game index
        :param full_grid: whether to print the full grid or only the visible part
        :param hightlighted: np.ndarray or one of ['losing', 'last_moves']
        :param plot_kwargs: args to utils.pyplot_game,
        """
        plot_kwargs['state'] = self.numbers[idx] if full_grid else self.game_state()[idx]
        if isinstance(highlighted, np.ndarray):
            plot_kwargs['highlighted'] = highlighted
        elif highlighted == 'losing':
            plot_kwargs['highlighted'] = self.losing_moves()[idx]
        elif highlighted == 'last_moves':
            plot_kwargs['highlighted'] = self.last_flagged[idx] - self.last_opened[idx]
        return utils.pyplot_game(**plot_kwargs)

    def as_dataset(self) -> np.ndarray:
        """returns the current state as an np.int8 ndarray (n,w,h) with:
         - -1: mine
         - 0-8: open cell with the number
         - 9: closed cell
         - 10: flag"""
        return (self.numbers*self.open_cells
                + 9*(1 - self.open_cells - self.mines)
                - self.mines
                + 11*self.flags)
