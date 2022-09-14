// Copyright 2022 The etcd Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package e2e

import (
	"strings"

	"go.uber.org/zap"

	"go.etcd.io/etcd/pkg/v3/expect"
)

func SpawnCmd(args []string, envVars map[string]string) (*expect.ExpectProcess, error) {
	return SpawnNamedCmd(strings.Join(args, "_"), args, envVars)
}

func SpawnNamedCmd(processName string, args []string, envVars map[string]string) (*expect.ExpectProcess, error) {
	return SpawnCmdWithLogger(zap.NewNop(), args, envVars, processName)
}
