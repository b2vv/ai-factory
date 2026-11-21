package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"slices"
	"strings"
	"testing"
)

func TestDocument(t *testing.T) {
	source, _ := url.Parse("https://example.org/docs/setup/page")
	input := `<!doctype html><title>Setup</title><nav>Ignore menu</nav><main><h1>Install</h1>
	<p><a href="../guide">Guide</a> and <a href="javascript:void(0)">note</a></p>
	<pre><code class="language-sh">npm install &amp;&amp; npm test</code></pre>
	<table><tr><th>Engine</th><th>Version</th></tr><tr><td>Node</td><td>24</td></tr></table>
	<script>ignore script</script><footer>Ignore footer</footer></main>`
	got, err := convert(strings.NewReader(input), source)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"# Install", "[Guide](https://example.org/docs/guide)", "npm install && npm test", "```", "| Engine | Version |", "| Node | 24 |"} {
		if !strings.Contains(got.Markdown, want) {
			t.Errorf("missing %q in %s", want, got.Markdown)
		}
	}
	for _, forbidden := range []string{"Ignore menu", "Ignore footer", "ignore script", "javascript:"} {
		if strings.Contains(got.Markdown, forbidden) {
			t.Errorf("retained %q", forbidden)
		}
	}
	if got.Source != source.String() || got.Extraction != "main" || len(got.Warnings) != 0 {
		t.Errorf("metadata: %+v", got)
	}
}

func TestCoverageWarnings(t *testing.T) {
	source, _ := url.Parse("https://example.org/")
	cases := []struct{ input, warning string }{
		{"<p>Still useful</p>", "main_not_identified"},
		{"<main>One</main><main>Two</main>", "multiple_main_regions"},
		{"<main><table><tr><td colspan=999999>Useful</td></tr></table></main>", "complex_table_flattened"},
	}
	for _, tc := range cases {
		got, err := convert(strings.NewReader(tc.input), source)
		if err != nil || !slices.Contains(got.Warnings, tc.warning) {
			t.Errorf("%q: %+v, %v", tc.warning, got, err)
		}
	}
	if _, err := convert(strings.NewReader("<div id=root></div><script></script>"), source); err == nil {
		t.Fatal("empty app shell reported success")
	}
}

func TestPublicDestination(t *testing.T) {
	for _, ip := range []string{"8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"} {
		if !publicIP(netip.MustParseAddr(ip)) {
			t.Errorf("rejected %s", ip)
		}
	}
	for _, ip := range []string{"0.0.0.0", "10.1.2.3", "127.0.0.1", "100.64.0.1", "169.254.169.254", "192.0.2.1", "224.0.0.1", "::1", "fc00::1", "fe80::1", "64:ff9b::808:808", "2002:7f00:1::1", "::ffff:127.0.0.1"} {
		if publicIP(netip.MustParseAddr(ip)) {
			t.Errorf("accepted %s", ip)
		}
	}
}

func TestURLPolicy(t *testing.T) {
	for _, raw := range []string{"https://example.org/docs", "http://example.org:80/"} {
		u, _ := url.Parse(raw)
		if err := checkURL(u); err != nil {
			t.Error(err)
		}
	}
	for _, raw := range []string{"file:///etc/hosts", "https://user@example.org", "http://localhost./", "http://archive.local", "http://127.0.0.1", "https://example.org:8080", "/relative"} {
		u, _ := url.Parse(raw)
		if checkURL(u) == nil {
			t.Errorf("accepted %s", raw)
		}
	}
}

func TestDialPinsValidatedAddress(t *testing.T) {
	for _, mixed := range []bool{false, true} {
		t.Run(map[bool]string{false: "public", true: "mixed"}[mixed], func(t *testing.T) {
			calls := 0
			connect := publicDial(func(_ context.Context, network, host string) ([]netip.Addr, error) {
				if network != "ip" || host != "example.org." {
					t.Fatalf("unexpected lookup %s %s", network, host)
				}
				addresses := []netip.Addr{netip.MustParseAddr("8.8.8.8")}
				if mixed {
					addresses = append(addresses, netip.MustParseAddr("127.0.0.1"))
				}
				return addresses, nil
			}, func(_ context.Context, network, addr string) (net.Conn, error) {
				calls++
				if network != "tcp" || addr != "8.8.8.8:443" {
					t.Fatalf("unexpected dial %s %s", network, addr)
				}
				return nil, errors.New("fixture: no socket dialed")
			})
			_, err := connect(context.Background(), "tcp", "example.org:443")
			if err == nil || (!mixed && calls != 1) || (mixed && calls != 0) {
				t.Fatalf("calls=%d err=%v", calls, err)
			}
		})
	}
}

func TestRedirectPolicy(t *testing.T) {
	original, _ := http.NewRequest("GET", "https://example.org/private-path", nil)
	for _, x := range []struct {
		dest  string
		count int
		allow bool
	}{
		{"https://other.example.org/docs", 3, true}, {"https://other.example.org/docs", 4, false},
		{"https://127.0.0.1/", 1, false}, {"http://example.org/downgrade", 1, false},
	} {
		next, _ := http.NewRequest("GET", x.dest, nil)
		next.Header.Set("Referer", original.URL.String())
		err := redirectPolicy(next, slices.Repeat([]*http.Request{original}, x.count))
		if x.allow != (err == nil) || x.allow && next.Header.Get("Referer") != "" {
			t.Errorf("%s: %v", x.dest, err)
		}
	}
}

func TestByteLimit(t *testing.T) {
	for _, n := range []int{maxBytes, maxBytes + 1} {
		data, err := readBounded(io.LimitReader(strings.NewReader(strings.Repeat("x", n)), int64(n)))
		if n == maxBytes && (err != nil || len(data) != n) || n > maxBytes && err == nil {
			t.Fatalf("read %d: received %d, error %v", n, len(data), err)
		}
	}
}

func TestExpandedContentLimits(t *testing.T) {
	base, _ := url.Parse("https://example.org/" + strings.Repeat("p", 3000) + "/page")
	links := "<main>" + strings.Repeat("<a href=\"x\">x</a>", 100) + "</main>"
	if _, err := convert(strings.NewReader(links), base); err == nil || !strings.Contains(err.Error(), "resolved links") {
		t.Fatalf("link budget: %v", err)
	}
	rows := "<main><table><tr>" + strings.Repeat("<td>cell</td>", 200) + "</tr>" + strings.Repeat("<tr><td>cell</td></tr>", 90) + "</table></main>"
	if _, err := convert(strings.NewReader(rows), base); err == nil || !strings.Contains(err.Error(), "table grid") {
		t.Fatalf("table budget: %v", err)
	}
}

func TestCLIOutput(t *testing.T) {
	const source = "https://example.org/guide"
	load := func(_ context.Context, url string) (result, error) {
		if url != source {
			t.Fatalf("unexpected URL %q", url)
		}
		return result{Source: source, Extraction: "body", Markdown: "# Guide", Warnings: []string{"main_not_identified"}}, nil
	}
	var stdout, stderr strings.Builder
	if code := run([]string{source}, &stdout, &stderr, load); code != 0 || stderr.Len() != 0 {
		t.Fatalf("JSON run: %d, %q", code, stderr.String())
	}
	var parsed result
	if err := json.Unmarshal([]byte(stdout.String()), &parsed); err != nil || parsed.Source != source || !slices.Equal(parsed.Warnings, []string{"main_not_identified"}) {
		t.Fatalf("JSON metadata: %+v, %v", parsed, err)
	}
	stdout.Reset()
	if code := run([]string{"--markdown", source}, &stdout, &stderr, load); code != 0 || stdout.String() != "# Guide\n" || stderr.String() != "warning: main_not_identified\n" {
		t.Fatalf("Markdown run: %d, %q, %q", code, stdout.String(), stderr.String())
	}
	stdout.Reset()
	stderr.Reset()
	if code := run([]string{"--markdown"}, &stdout, &stderr, load); code != 2 || stdout.Len() != 0 || !strings.HasPrefix(stderr.String(), "usage:") {
		t.Fatalf("usage: %d, %q, %q", code, stdout.String(), stderr.String())
	}
	stderr.Reset()
	fail := func(context.Context, string) (result, error) { return result{}, errors.New("fetch failed") }
	if code := run([]string{"--markdown", source}, &stdout, &stderr, fail); code != 1 || stdout.Len() != 0 || stderr.String() != "fetch failed\n" {
		t.Fatalf("failure: %d, %q, %q", code, stdout.String(), stderr.String())
	}
}
