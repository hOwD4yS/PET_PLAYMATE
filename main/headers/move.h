#ifndef MOVE_H
#define MOVE_H

#include <Arduino.h>

class Move {
public:
  Move(int lspeed, int lin, int lout, int rin, int rout, int rspeed);
  void forward(int distance);
  void backward(int distance);
  void left();
  void right();
  void stop();

private:
  int PIN_LIN, PIN_LOUT, PIN_LSPEED;
  int PIN_RIN, PIN_ROUT, PIN_RSPEED;
};

#endif
