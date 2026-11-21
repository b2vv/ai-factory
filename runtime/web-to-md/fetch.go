package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"strings"
	"time"

	"golang.org/x/net/html/charset"
)

const (
	maxBytes       = 2 << 20
	requestTimeout = 12 * time.Second
)

var nonPublic = prefixes(
	"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
	"172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
	"198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/3",
	"2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
)
var globalV6 = netip.MustParsePrefix("2000::/3")

func prefixes(values ...string) []netip.Prefix {
	ps := make([]netip.Prefix, 0, len(values))
	for _, v := range values {
		ps = append(ps, netip.MustParsePrefix(v))
	}
	return ps
}

func publicIP(addr netip.Addr) bool {
	addr = addr.Unmap()
	if !addr.IsGlobalUnicast() || addr.Zone() != "" || (addr.Is6() && !globalV6.Contains(addr)) {
		return false
	}
	for _, p := range nonPublic {
		if p.Contains(addr) {
			return false
		}
	}
	return true
}

func checkURL(u *url.URL) error {
	if u == nil || (u.Scheme != "http" && u.Scheme != "https") ||
		u.User != nil || u.Opaque != "" || len(u.String()) > 4096 {
		return errors.New("expected a public HTTP(S) URL without user information")
	}
	host := strings.TrimSuffix(strings.ToLower(u.Hostname()), ".")
	if p := u.Port(); p != "" && (u.Scheme == "http" && p != "80" || u.Scheme == "https" && p != "443") {
		return errors.New("only the scheme's default port is allowed")
	}
	if ip, err := netip.ParseAddr(host); err == nil {
		if !publicIP(ip) {
			return errors.New("non-public destination")
		}
		return nil
	}
	for _, suffix := range []string{".localhost", ".local", ".internal", ".home.arpa", ".onion"} {
		if strings.HasSuffix(host, suffix) {
			return errors.New("local or special-use hostname")
		}
	}
	if !strings.Contains(host, ".") || strings.ContainsAny(host, "%:") {
		return errors.New("expected a fully qualified public hostname")
	}
	return nil
}

type resolverFunc func(context.Context, string, string) ([]netip.Addr, error)
type dialFunc func(context.Context, string, string) (net.Conn, error)

func publicDial(resolve resolverFunc, dial dialFunc) dialFunc {
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil {
			return nil, err
		}
		var ips []netip.Addr
		if ip, err := netip.ParseAddr(host); err == nil {
			ips = []netip.Addr{ip}
		} else {
			ips, err = resolve(ctx, "ip", strings.TrimSuffix(host, ".")+".")
			if err != nil {
				return nil, err
			}
		}
		if len(ips) == 0 || len(ips) > 32 {
			return nil, errors.New("invalid DNS address count")
		}
		for _, ip := range ips {
			if !publicIP(ip) {
				return nil, errors.New("DNS contained a non-public address")
			}
		}
		for _, ip := range ips {
			conn, dialErr := dial(ctx, network, net.JoinHostPort(ip.Unmap().String(), port))
			if dialErr == nil {
				return conn, nil
			}
			err = dialErr
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
		}
		return nil, err
	}
}

func redirectPolicy(req *http.Request, via []*http.Request) error {
	if len(via) > 3 {
		return errors.New("too many redirects")
	}
	if err := checkURL(req.URL); err != nil {
		return err
	}
	if via[len(via)-1].URL.Scheme == "https" && req.URL.Scheme != "https" {
		return errors.New("HTTPS downgrade refused")
	}
	req.Header.Del("Referer")
	return nil
}

func fetch(ctx context.Context, raw string) (result, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return result{}, errors.New("invalid URL")
	}
	if err := checkURL(u); err != nil {
		return result{}, err
	}
	u.Fragment, u.RawFragment = "", ""
	dialer := &net.Dialer{Timeout: 3 * time.Second}
	transport := &http.Transport{
		DialContext:       publicDial(net.DefaultResolver.LookupNetIP, dialer.DialContext),
		DisableKeepAlives: true, MaxResponseHeaderBytes: 64 << 10,
		TLSHandshakeTimeout: 4 * time.Second, ResponseHeaderTimeout: 6 * time.Second,
	}
	client := &http.Client{Transport: transport, Timeout: requestTimeout, CheckRedirect: redirectPolicy}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return result{}, err
	}
	req.Header.Set("Accept", "text/html, application/xhtml+xml")
	req.Header.Set("User-Agent", "AI-Factory-web-to-md/0.1")
	resp, err := client.Do(req)
	if err != nil {
		return result{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return result{}, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	contentType := resp.Header.Get("Content-Type")
	media, _, err := mime.ParseMediaType(contentType)
	if err != nil || (media != "text/html" && media != "application/xhtml+xml") {
		return result{}, errors.New("response is not HTML")
	}
	if resp.Header.Get("Content-Encoding") != "" && !strings.EqualFold(resp.Header.Get("Content-Encoding"), "identity") {
		return result{}, errors.New("unsupported response encoding")
	}
	input, err := readBounded(resp.Body)
	if err != nil {
		return result{}, err
	}
	decoded, err := charset.NewReader(strings.NewReader(string(input)), contentType)
	if err != nil {
		return result{}, err
	}
	return convert(decoded, resp.Request.URL)
}

func readBounded(r io.Reader) ([]byte, error) {
	b, err := io.ReadAll(io.LimitReader(r, maxBytes+1))
	if err != nil {
		return nil, err
	}
	if len(b) > maxBytes {
		return nil, errors.New("HTML exceeds 2 MiB limit")
	}
	return b, nil
}
