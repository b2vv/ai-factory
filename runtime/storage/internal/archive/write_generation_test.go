package archive

import "testing"

func TestNoteWriteAdvancesGeneration(t *testing.T) {
	before := WriteGeneration()
	noteWrite()
	if WriteGeneration() == before {
		t.Fatal("a write must change the generation")
	}
}
