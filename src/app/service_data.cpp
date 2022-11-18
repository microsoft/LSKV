// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "service_data.h"
#include "ccf/app_interface.h"
#include "service/tables/service.h"

namespace app::service_data {

  PublicPrefixes get_public_prefixes(kv::ReadOnlyTx& tx) {
      auto ccf_governance_map =
        tx.template ro<ccf::Service>(ccf::Tables::SERVICE);
      CCF_APP_DEBUG("Getting service_info map");
      auto service_info_opt = ccf_governance_map->get();
      if (!service_info_opt.has_value()) {
      CCF_APP_DEBUG("Service info had no value, returning early");
          return {};
      }
      CCF_APP_DEBUG("Extracting service data");
      auto service_data = service_info_opt.value().service_data;
      ServiceData sd;
      try {
          CCF_APP_DEBUG("Parsing service data: {}", service_data);
          sd = service_data.get<ServiceData>();
      }
      catch (nlohmann::json::exception e) {
          CCF_APP_DEBUG("Failed to get service data from json: {}", e.what());
      }
      return sd.public_prefixes;
  }
} // namespace app::service_data
