package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"syscall"
	"time"
)

type stage struct {
	Name   string `json:"name"`
	State  string `json:"state"`
	Detail string `json:"detail"`
	Source string `json:"source,omitempty"`
}
type project struct {
	ID          string             `json:"id"`
	Name        string             `json:"name"`
	Task        string             `json:"task"`
	State       string             `json:"state"`
	Revision    string             `json:"revision"`
	Observed    string             `json:"observed,omitempty"`
	Next        string             `json:"next"`
	Stages      []stage            `json:"stages"`
	DetailID    string             `json:"detailId,omitempty"`
	DetailToken string             `json:"detailToken,omitempty"`
	Provenance  string             `json:"provenance,omitempty"`
	Workflow    string             `json:"workflow,omitempty"`
	Transition  *transitionDisplay `json:"transition,omitempty"`
}
type snapshot struct {
	CheckedAt time.Time `json:"checkedAt"`
	Projects  []project `json:"projects"`
}

var revisionPattern = regexp.MustCompile(`^[a-f0-9]{40}$`)

func boundedFile(dir *os.Root, path string, limit int64) (*os.File, fs.FileInfo, error) {
	info, err := dir.Lstat(path)
	if err != nil {
		return nil, nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > limit {
		return nil, nil, fmt.Errorf("invalid evidence file")
	}
	f, err := dir.OpenFile(path, os.O_RDONLY|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, nil, err
	}
	post, err := f.Stat()
	if err != nil || !os.SameFile(info, post) || post.Size() != info.Size() {
		f.Close()
		return nil, nil, fmt.Errorf("evidence changed while opening")
	}
	return f, post, nil
}

func readGitFile(dir *os.Root, path string, limit int64) (string, error) {
	f, info, err := boundedFile(dir, path, limit)
	if err != nil {
		return "", err
	}
	defer f.Close()
	raw, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil || int64(len(raw)) != info.Size() {
		return "", fmt.Errorf("git metadata changed while reading")
	}
	return string(raw), nil
}

var headRefPattern = regexp.MustCompile(`^refs/heads/[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$`)

func revision(root string) string {
	dir, err := os.OpenRoot(filepath.Join(root, ".git"))
	if err != nil {
		return ""
	} // A worktree gitfile is intentionally unsupported.
	defer dir.Close()
	head, err := readGitFile(dir, "HEAD", 1024)
	if err != nil {
		return ""
	}
	value := strings.TrimSpace(head)
	if revisionPattern.MatchString(value) {
		return value
	}
	ref, ok := strings.CutPrefix(value, "ref: ")
	if !ok || !headRefPattern.MatchString(ref) || strings.Contains(ref, "..") {
		return ""
	}
	raw, err := readGitFile(dir, ref, 1024)
	if err == nil {
		id := strings.TrimSpace(raw)
		if !revisionPattern.MatchString(id) {
			return ""
		}
		return id
	}
	if !os.IsNotExist(err) {
		return ""
	}
	packed, err := readGitFile(dir, "packed-refs", 2<<20)
	if err != nil {
		return ""
	}
	result := ""
	for line := range strings.SplitSeq(packed, "\n") {
		id, name, ok := strings.Cut(line, " ")
		if !ok || name != ref {
			continue
		}
		if result != "" || !revisionPattern.MatchString(id) {
			return ""
		}
		result = id
	}
	return result
}

func base(id, name, task, head string) project {
	short := "Unknown"
	if revisionPattern.MatchString(head) {
		short = head[:8]
	}
	p := project{ID: id, Name: name, Task: task, State: "Unknown", Revision: short, Next: "Запис або ревізія змінилися чи недоступні. Поточний прогрес невідомий."}
	for _, s := range []string{"Plan", "Implementation", "Tests", "Review", "Push", "Update"} {
		p.Stages = append(p.Stages, stage{s, "Unknown", "Немає перевіреного доказу для цього етапу.", ""})
	}
	return p
}

// roots holds the private feed; project checkouts come from the configured registry.
type roots struct{ feed string }

func (r roots) repo(id string) string { return projects.root(id) }
func (r roots) snapshot() snapshot {
	now := time.Now()
	out := snapshot{CheckedAt: now.UTC()}
	for _, id := range projects.ids {
		p, _ := r.readOne(id, now)
		out.Projects = append(out.Projects, p)
	}
	return out
}

func dashboardHeaders(w http.ResponseWriter) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
	w.Header().Set("Cross-Origin-Resource-Policy", "same-origin")
}

func dashboardNavigation(r *http.Request) bool {
	return r.Method == http.MethodGet && r.URL.Path == "/" && r.Header.Get("Sec-Fetch-Mode") == "navigate" && r.Header.Get("Sec-Fetch-Dest") == "document"
}

func dashboard(host string, read func(context.Context) snapshot, readProject func(string) (project, feedRecord)) http.Handler {
	return dashboardAtOrigin(host, "http://"+host, read, readProject)
}

func dashboardAtOrigin(host, origin string, read func(context.Context) snapshot, readProject func(string) (project, feedRecord)) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dashboardHeaders(w)
		// A normal top-level link can open the shell, but cross-site readers,
		// subresources, API calls and frames cannot consume dashboard data.
		if r.Host != host || r.Header.Get("Origin") != "" && r.Header.Get("Origin") != origin || r.Header.Get("Sec-Fetch-Site") == "cross-site" && !dashboardNavigation(r) {
			http.Error(w, "Forbidden", http.StatusForbidden)
			return
		}
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if r.URL.RawQuery != "" || r.URL.RawPath != "" {
			http.NotFound(w, r)
			return
		}
		if id, hasPrefix := strings.CutPrefix(r.URL.Path, "/api/details/"); hasPrefix {
			projectID := projects.details[id]
			if projectID == "" || readProject == nil {
				http.NotFound(w, r)
				return
			}
			card, report := readProject(projectID)
			if card.DetailToken == "" || report.Markdown == "" || projects.aliases[id] != "" && projects.aliases[id] != report.TaskID {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("Content-Type", "text/markdown; charset=utf-8")
			w.Header().Set("X-Dashboard-Detail-Token", card.DetailToken)
			_, _ = w.Write([]byte(report.Markdown))
			return
		}

		if r.URL.Path == "/api/status" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(read(r.Context()))
			return
		}
		items := map[string][2]string{
			"/":          {"ui/index.html", "text/html; charset=utf-8"},
			"/style.css": {"ui/style.css", "text/css; charset=utf-8"},
			"/app.js":    {"ui/dist/app.js", "text/javascript; charset=utf-8"},
		}
		item, ok := items[r.URL.Path]
		if !ok {
			http.NotFound(w, r)
			return
		}
		data, err := fs.ReadFile(assets, item[0])
		if err != nil {
			http.Error(w, "Asset unavailable", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", item[1])
		_, _ = w.Write(data)
	})
}

func main() {
	projectsPath := flag.String("projects", os.Getenv("DASHBOARD_PROJECTS"), "absolute path to the projects JSON config outside the kit (default $DASHBOARD_PROJECTS)")
	rootsUnder := flag.String("roots-under", "", "replace every configured root with DIR/<id> (read-only container mounts)")
	listProjects := flag.Bool("list-projects", false, "validate the projects config and print one id<TAB>root line per project, then exit")
	feedRoot := flag.String("feed", "feed", "private status directory, or read-only mount in Docker")
	publish := flag.Bool("publish", false, "validate one status JSON record from stdin; dry-run by default")
	transition := flag.Bool("publish-transition", false, "validate and optionally write one metadata-only workflow transition from stdin")
	apply := flag.Bool("apply", false, "atomically publish the validated JSON instead of dry-run")
	port := flag.Int("port", 8732, "local IPv4 port; 0 selects a temporary free port")
	container := flag.Bool("container", false, "listen on the container bridge; publish only a host loopback port")
	probe := flag.Bool("probe", false, "verify architecture and local shell health inside the container, then exit")
	shareHost := flag.String("share-host", "", "exact assigned share hostname, one label under -share-domain (selects a separate share listener)")
	shareDomain := flag.String("share-domain", "", "required with sharing: the share provider's domain, e.g. share.example.test")
	shareAuth := flag.Bool("share-auth", false, "allow only configured logins on the share listener; otherwise return 403")
	shareDigest := flag.String("share-digest", "", "mode-0600 file with one login, role, and password digest per line")
	flag.Parse()
	sources := roots{*feedRoot}
	if flag.NArg() != 0 || *apply && !*publish && !*transition || *publish && *transition || *listProjects && (*publish || *transition || *probe) {
		log.Fatal("invalid arguments; see -help")
	}
	if !*probe {
		registry, err := loadProjects(*projectsPath, *rootsUnder)
		if err != nil {
			log.Fatalf("invalid projects config (-projects or DASHBOARD_PROJECTS): %v", err)
		}
		projects = registry
	}
	if *listProjects {
		for _, id := range projects.ids {
			fmt.Printf("%s\t%s\n", id, projects.root(id))
		}
		return
	}
	sharing := false
	flag.Visit(func(f *flag.Flag) {
		if f.Name == "share-host" || f.Name == "share-domain" || f.Name == "share-digest" || f.Name == "share-auth" {
			sharing = true
		}
	})
	var shareHandler http.Handler
	if sharing {
		if *publish || *transition || *probe || *port == 8732 || !validShareHost(*shareHost, *shareDomain) {
			log.Fatal("share mode requires its own port, -share-domain and an exact host one label under it")
		}
		shareHandler = http.HandlerFunc(shareForbidden)
		if *shareAuth {
			users, err := loadShareAccounts(*shareDigest)
			if err != nil {
				log.Fatal("invalid share credentials file")
			}
			owner := dashboardAtOrigin(*shareHost, "https://"+*shareHost, func(_ context.Context) snapshot { return sources.snapshot() }, func(id string) (project, feedRecord) { return sources.readOne(id, time.Now()) })
			shareHandler = sharedDashboard(*shareHost, users, owner, sources.snapshot)
		}
	}

	if *publish || *transition {
		if *container || *probe {
			log.Fatal("publishing runs on host only")
		}
		write := sources.publish
		if *transition {
			write = sources.publishTransition
		}
		if err := write(os.Stdin, *apply, time.Now()); err != nil {
			log.Fatal(err)
		}
		if *apply {
			fmt.Println("Status published atomically.")
		} else {
			fmt.Println("Dry run: valid status for current HEAD; no writes.")
		}
		return
	}
	if *port < 0 || *port > 65535 {
		log.Fatal("Invalid port")
	}
	address := fmt.Sprintf("127.0.0.1:%d", *port)
	if *probe {
		if runtime.GOOS != "linux" || runtime.GOARCH != "amd64" || os.Geteuid() == 0 {
			log.Fatal("expected a non-root linux/amd64 process")
		}
		client := http.Client{Timeout: 2 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
		res, err := client.Get("http://" + address + "/")
		if err != nil {
			log.Fatal(err)
		}
		defer res.Body.Close()
		if res.StatusCode != http.StatusOK {
			log.Fatal("dashboard health probe failed")
		}
		fmt.Printf("%s/%s uid=%d HTTP %d\n", runtime.GOOS, runtime.GOARCH, os.Geteuid(), res.StatusCode)
		return
	}
	bind := address
	if *container {
		if *port == 0 {
			log.Fatal("container requires a fixed port")
		}
		bind = fmt.Sprintf("0.0.0.0:%d", *port)
	}
	listener, err := net.Listen("tcp4", bind)
	if err != nil {
		log.Fatal(err)
	}
	host := address
	if !*container {
		host = listener.Addr().String()
	}
	handler := shareHandler
	if handler == nil {
		handler = dashboard(host, func(_ context.Context) snapshot { return sources.snapshot() }, func(id string) (project, feedRecord) { return sources.readOne(id, time.Now()) })
	}
	srv := &http.Server{Handler: handler, DisableGeneralOptionsHandler: sharing, ReadHeaderTimeout: 3 * time.Second, ReadTimeout: 4 * time.Second, WriteTimeout: 8 * time.Second, IdleTimeout: 20 * time.Second, MaxHeaderBytes: 16 << 10}
	if sharing {
		fmt.Println("Factory shared dashboard ready on the separate listener")
	} else {
		fmt.Printf("Factory dashboard: http://%s/\n", host)
	}
	log.Fatal(srv.Serve(listener))
}
