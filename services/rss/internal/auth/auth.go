// Package auth resolves the owner identity for each request.
package auth

import (
	"context"
	"errors"
	"net/http"
)

var ErrUnauthorized = errors.New("unauthorized")

// Authorizer returns the owner ID for a request: "self" in self-host mode,
// the Supabase user UUID (JWT sub claim) in managed mode.
type Authorizer interface {
	OwnerID(r *http.Request) (string, error)
}

// SelfAuth treats every caller as the single owner. In self-host the tunnel
// URL IS the capability — anyone who can reach the service is the owner.
type SelfAuth struct{}

func (SelfAuth) OwnerID(*http.Request) (string, error) { return "self", nil }

type ownerCtxKey struct{}

func WithOwner(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, ownerCtxKey{}, id)
}

func OwnerFrom(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(ownerCtxKey{}).(string)
	return id, ok
}

func RequireOwner(a Authorizer) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			id, err := a.OwnerID(r)
			if err != nil {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r.WithContext(WithOwner(r.Context(), id)))
		})
	}
}
