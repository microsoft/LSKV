// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/ds/json.h"

#include <string>
#include <vector>

namespace app::nodes
{
  struct NodeData
  {
    std::string name;
    std::vector<std::string> peer_urls;
    std::vector<std::string> client_urls;
  };

  DECLARE_JSON_TYPE(NodeData);
  DECLARE_JSON_REQUIRED_FIELDS(NodeData, name, peer_urls, client_urls);
} // namespace app::nodes
