package archive

import "sync/atomic"

// writeGeneration changes after every archive write this process makes through any
// MongoStore. Inventory caches use it as an exact "nothing written since" token.
var writeGeneration atomic.Uint64

// WriteGeneration returns the current process-wide archive write generation. It is
// advanced after a write call returns, successful or not, so a reader that takes the
// token before measuring can never claim freshness past a write it did not see.
func WriteGeneration() uint64 { return writeGeneration.Load() }

func noteWrite() { writeGeneration.Add(1) }
