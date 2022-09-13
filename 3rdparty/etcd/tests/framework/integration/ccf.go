package integration

import (
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"testing"
	"time"

	"go.etcd.io/etcd/client/pkg/v3/testutil"
	clientv3 "go.etcd.io/etcd/client/v3"
)

const (
	defaultPort = "8000"
	defaultHost = "127.0.0.1"
)

type CcfCluster struct {
	cmd *exec.Cmd
	t   testing.TB
	ctx context.Context
}

func NewCcfCluster(t testing.TB, ctx context.Context) *CcfCluster {
	sandbox := "/opt/ccf/bin/sandbox.sh"
	if _, err := os.Stat(sandbox); err != nil {
		t.Fatalf("failed to find sandbox: %v", err)
	}
	ccfkvsdir_var := "CCF_KVS_DIR"
	ccf_kvs_dir := os.Getenv(ccfkvsdir_var)
	if ccf_kvs_dir == "" {
		t.Fatalf("failed to get %v env variable", ccfkvsdir_var)
	}

	enclave := fmt.Sprintf("%v/build/libccf_kvs.virtual.so", ccf_kvs_dir)
	if _, err := os.Stat(enclave); err != nil {
		fmt.Printf("current dir: %v\n", os.Getenv("PWD"))
		t.Fatalf("failed to find enclave: %v", err)
	}

	cmd := exec.Command(sandbox, "-p", enclave, "--http2")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	fmt.Printf("starting sandbox: %v\n", cmd)

	err := cmd.Start()
	if err != nil {
		t.Fatalf("failed to start sandbox: %v", err)
	}

	waitForPort(net.JoinHostPort(defaultHost, defaultPort))
	return &CcfCluster{
		cmd: cmd,
		t:   t,
		ctx: ctx,
	}
}

// wait for port to be up
func waitForPort(address string) {
	timeout := time.Second
	for {
		conn, err := net.DialTimeout("tcp", address, timeout)
		if err == nil {
			fmt.Printf("port open (%v)\n", address)
			conn.Close()
			time.Sleep(time.Second)
			return
		}
		time.Sleep(timeout)
		fmt.Printf("waiting on port (%v)\n", address)
	}
}

func (c *CcfCluster) Members() []CcfMember {
	// TODO
	return nil
}

func (c *CcfCluster) Client() (*clientv3.Client, error) {
	endpoints := fmt.Sprintf("https://%v", net.JoinHostPort(defaultHost, defaultPort))
	conf, err := clientv3.NewClientConfig(&clientv3.ConfigSpec{
		Endpoints: []string{endpoints},
		Secure: &clientv3.SecureConfig{
			InsecureTransport:  true,
			InsecureSkipVerify: true,
		},
	}, nil)
	if err != nil {
		return nil, err
	}
	client, err := clientv3.New(*conf)
	if err != nil {
		return nil, err
	}
	return client, nil
}

func (c *CcfCluster) WaitLeader(t testing.TB) int {
	// TODO
	return 0
}

func (c *CcfCluster) Close() error {
	fmt.Println("killing sandbox")
	err := c.cmd.Process.Kill()
	if err != nil {
		return err
	}
	err = c.cmd.Wait()
	return err
}

type ccfClient struct{}

type CcfMember struct {
	Client *clientv3.Client
}

// Restart starts the member using the preserved data dir.
func (c *CcfMember) Restart(t testutil.TB) error {
	// TODO
	return nil
}

// Stop stops the member, but the data dir of the member is preserved.
func (c *CcfMember) Stop(t testutil.TB) {
	// TODO
}
