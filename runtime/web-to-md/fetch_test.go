package main

import (
	"bytes"
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"net/url"
	"strings"
	"testing"
	"time"
)

func convertString(t *testing.T, input string) result {
	t.Helper()
	source, _ := url.Parse("https://example.org/page")
	got, err := convert(strings.NewReader(input), source)
	if err != nil {
		t.Fatalf("convert: %v", err)
	}
	return got
}

func TestFormWrappedMain(t *testing.T) {
	got := convertString(t, `<body><form><main><h1>Doc</h1><p>Real content</p></main></form></body>`)
	if got.Extraction != "main" || !strings.Contains(got.Markdown, "# Doc") || !strings.Contains(got.Markdown, "Real content") {
		t.Fatalf("%+v", got)
	}
	got = convertString(t, `<main><form><label>Name</label><input value="typed"><select><option>Choice</option></select>
		<textarea>Draft</textarea><button>Send</button><datalist><option>Hint</option></datalist><p>Form text</p></form></main>`)
	for _, gone := range []string{"typed", "Choice", "Draft", "Send", "Hint"} {
		if strings.Contains(got.Markdown, gone) {
			t.Errorf("kept control text %q: %s", gone, got.Markdown)
		}
	}
	for _, kept := range []string{"Name", "Form text"} {
		if !strings.Contains(got.Markdown, kept) {
			t.Errorf("lost %q: %s", kept, got.Markdown)
		}
	}
}

func TestRoleTokens(t *testing.T) {
	for _, role := range []string{"Main", "main banner", " MAIN "} {
		got := convertString(t, `<div>Menu</div><div role="`+role+`"><p>Body text</p></div>`)
		if got.Extraction != "main" || strings.Contains(got.Markdown, "Menu") {
			t.Errorf("role %q: %+v", role, got)
		}
	}
}

func TestHeaders(t *testing.T) {
	got := convertString(t, `<header>Site banner</header><article><header><h1>Post title</h1></header><p>Post body</p></article>`)
	if strings.Contains(got.Markdown, "Site banner") || !strings.Contains(got.Markdown, "# Post title") {
		t.Errorf("article: %s", got.Markdown)
	}
	got = convertString(t, `<header>Site banner</header><p>Loose text</p>`)
	if strings.Contains(got.Markdown, "Site banner") || !strings.Contains(got.Markdown, "Loose text") {
		t.Errorf("body: %s", got.Markdown)
	}
	got = convertString(t, `<header><main><p>Wrapped main</p></main></header>`)
	if got.Extraction != "main" || !strings.Contains(got.Markdown, "Wrapped main") {
		t.Errorf("wrapping header: %+v", got)
	}
}

func TestImageAlt(t *testing.T) {
	got := convertString(t, "<main><p>See <img src=a.png alt=\"  Install\n  diagram \"> and <img src=b.png alt=\"\"><img src=c.png>.</p></main>")
	if !strings.Contains(got.Markdown, "See Install diagram and") || strings.Contains(got.Markdown, "png") {
		t.Errorf("%q", got.Markdown)
	}
	long := strings.Repeat("a", 300)
	got = convertString(t, `<main><p>x <img alt="`+long+`"></p></main>`)
	if strings.Contains(got.Markdown, strings.Repeat("a", 201)) || !strings.Contains(got.Markdown, strings.Repeat("a", 200)) {
		t.Errorf("alt not capped: %d", len(got.Markdown))
	}
}

func TestNumericHosts(t *testing.T) {
	for _, raw := range []string{"http://127.1/", "http://0x7f.0.0.1/", "http://1.2.3.0x4/", "http://0X7F.1/"} {
		u, _ := url.Parse(raw)
		if err := checkURL(u); err == nil || !strings.Contains(err.Error(), "numeric") {
			t.Errorf("%s: %v", raw, err)
		}
	}
	for _, raw := range []string{"https://example.org/", "https://8.8.8.8/", "https://1.example.org/"} {
		u, _ := url.Parse(raw)
		if err := checkURL(u); err != nil {
			t.Errorf("%s: %v", raw, err)
		}
	}
}

func TestDecodedLimitIsSeparate(t *testing.T) {
	big := "<main><p>" + strings.Repeat("x", maxBytes) + "</p></main>"
	source, _ := url.Parse("https://example.org/")
	if _, err := convert(strings.NewReader(big), source); err != nil && strings.Contains(err.Error(), "2 MiB") {
		t.Fatalf("decoded stream hit the raw cap: %v", err)
	}
	huge := io.LimitReader(neverEnding('x'), maxDecoded+1)
	if _, err := convert(huge, source); err == nil || !strings.Contains(err.Error(), "decoded HTML exceeds 6 MiB") {
		t.Fatalf("decoded cap: %v", err)
	}
}

type neverEnding byte

func (b neverEnding) Read(p []byte) (int, error) {
	for i := range p {
		p[i] = byte(b)
	}
	return len(p), nil
}

// serve runs fetchWith against an httptest server while the URL names a public host on the default port.
func serve(t *testing.T, handler http.HandlerFunc, raw string) (result, error) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	resolve := func(context.Context, string, string) ([]netip.Addr, error) {
		return []netip.Addr{netip.MustParseAddr("93.184.216.34")}, nil
	}
	dial := func(ctx context.Context, network, addr string) (net.Conn, error) {
		if addr != "93.184.216.34:80" {
			t.Fatalf("dial %s", addr)
		}
		var d net.Dialer
		return d.DialContext(ctx, network, srv.Listener.Addr().String())
	}
	return fetchWith(context.Background(), raw, resolve, dial)
}

func TestFetch(t *testing.T) {
	html := func(body string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			io.WriteString(w, body)
		}
	}
	got, err := serve(t, html("<main><h1>Hello</h1></main>"), "http://example.org/a#frag")
	if err != nil || got.Markdown != "# Hello" || got.Source != "http://example.org/a" {
		t.Fatalf("ok: %+v %v", got, err)
	}
	_, err = serve(t, func(w http.ResponseWriter, r *http.Request) { http.NotFound(w, r) }, "http://example.org/")
	if err == nil || err.Error() != "HTTP 404" {
		t.Errorf("404: %v", err)
	}
	_, err = serve(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, "{}")
	}, "http://example.org/")
	if err == nil || err.Error() != "response is not HTML" {
		t.Errorf("json: %v", err)
	}
	_, err = serve(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Header().Set("Content-Encoding", "br")
		io.WriteString(w, "xx")
	}, "http://example.org/")
	if err == nil || err.Error() != "unsupported response encoding" {
		t.Errorf("br: %v", err)
	}
	_, err = serve(t, html("<main>"+strings.Repeat("x", maxBytes+1)+"</main>"), "http://example.org/")
	if err == nil || err.Error() != "HTML exceeds 2 MiB limit" {
		t.Errorf("raw cap: %v", err)
	}
}

func TestFetchLegacyCharset(t *testing.T) {
	// 1.5 MB of windows-1252 decodes to about 3 MB of UTF-8; the script is dropped, so the Markdown stays small.
	body := []byte("<script>")
	body = append(body, bytes.Repeat([]byte("\xe9"), 1500000)...)
	body = append(body, "</script><main><p>caf\xe9 \xe9</p></main>"...)
	got, err := serve(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=windows-1252")
		w.Write(body)
	}, "http://example.org/")
	if err != nil || got.Markdown != "café é" {
		t.Fatalf("%v %q", err, got.Markdown[:min(20, len(got.Markdown))])
	}
}

func TestFetchRedirects(t *testing.T) {
	got, err := serve(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/old" {
			http.Redirect(w, r, "/new", http.StatusFound)
			return
		}
		w.Header().Set("Content-Type", "text/html")
		io.WriteString(w, "<main><a href=\"x\">Link</a></main>")
	}, "http://example.org/old")
	if err != nil || got.Source != "http://example.org/new" || !strings.Contains(got.Markdown, "http://example.org/x") {
		t.Fatalf("%+v %v", got, err)
	}
	_, err = serve(t, func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "http://127.0.0.1/admin", http.StatusFound)
	}, "http://example.org/")
	if err == nil || !strings.Contains(err.Error(), "non-public destination") {
		t.Fatalf("private redirect: %v", err)
	}
}

func TestClientWiring(t *testing.T) {
	c := newClient(nil, nil)
	tr, ok := c.Transport.(*http.Transport)
	if !ok || tr.Proxy != nil || !tr.DisableKeepAlives || tr.DialContext == nil ||
		tr.TLSHandshakeTimeout != 4*time.Second || tr.ResponseHeaderTimeout != 6*time.Second || tr.MaxResponseHeaderBytes != 64<<10 {
		t.Fatalf("transport: %+v", tr)
	}
	if c.Timeout != requestTimeout || c.CheckRedirect == nil {
		t.Fatalf("client: %v", c.Timeout)
	}
}
