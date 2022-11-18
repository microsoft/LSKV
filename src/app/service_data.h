// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

# pragma once

#include "ccf/app_interface.h"
#include <vector>
#include "kvstore.h"

namespace app::service_data {
  using PublicPrefixes = std::vector<kvstore::KVStore::K>;


  struct ServiceData {
      PublicPrefixes public_prefixes;
  };

  DECLARE_JSON_TYPE(ServiceData);
  DECLARE_JSON_REQUIRED_FIELDS(ServiceData, public_prefixes);

  ServiceData get_service_data(kv::ReadOnlyTx& tx);

} // namespace app::service_data
