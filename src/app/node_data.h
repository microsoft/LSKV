// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/ds/json.h"

#include <string>

namespace app::nodes
{
  struct NodeData
  {
    std::string name;
  };

  DECLARE_JSON_TYPE(NodeData);
  DECLARE_JSON_REQUIRED_FIELDS(NodeData, name);
} // namespace app::nodes
