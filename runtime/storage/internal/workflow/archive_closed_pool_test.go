package workflow

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jackc/puddle/v2"
	"testing"
	"time"
)

func TestArchiveUpgradeReturnsClosedPoolFailure(t *testing.T) {
	pool, err := pgxpool.New(context.Background(), "postgres://fixture:fixture@127.0.0.1:1/fixture?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	pool.Close()
	s := &PGStore{pool: pool, opTimeout: time.Second}
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("upgrade Begin failure panicked: %v", r)
		}
	}()
	if err := s.UpgradeArchiveMetadata(context.Background()); !errors.Is(err, puddle.ErrClosedPool) {
		t.Fatal("lost closed-pool failure", err)
	}
}
