package core

func (b *Mind) Travel(me *Self, gx, gy float64) (float64, float64) { return b.travel(me, gx, gy) }
func (b *Mind) SetNow(t float64)                                   { b.now = t }
