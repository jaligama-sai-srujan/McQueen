# coding=utf-8
# Copyright 2018 The Google AI Language Team Authors and The HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""BERT finetuning runner."""

from __future__ import absolute_import

import logging
import torch
from torch import nn


from pytorch_transformers.modeling_bert import BertPreTrainedModel, BertModel
from torch.nn import CrossEntropyLoss

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


class BertMCQWeightedSum(BertPreTrainedModel):
    def __init__(self, config,  tie_weights):
        super(BertMCQWeightedSum, self).__init__(config)
        self.bert = BertModel(config)
        self._dropout = nn.Dropout(config.hidden_dropout_prob)
        self._classification_layer = nn.Linear(config.hidden_size, 1)
        if tie_weights is True:
            self._weight_layer = self._classification_layer
        else:
            self._weight_layer = nn.Linear(config.hidden_size, 1)
        self.apply(self.init_weights)

    def forward(self,  # type: ignore
                input_ids,
                token_type_ids,
                input_mask,
                labels = None):

        debug = False

        # shape: batch_size*num_choices*max_premise_perchoice, max_len
        flat_input_ids = input_ids.view(-1, input_ids.size(-1))
        flat_token_type_ids = token_type_ids.view(-1, token_type_ids.size(-1))
        flat_attention_mask = input_mask.view(-1, input_mask.size(-1))

        # shape: batch_size*num_choices*max_premise_perchoice, hidden_dim
        _, pooled_ph, attn = self.bert(input_ids=flat_input_ids,
                                       token_type_ids=flat_token_type_ids,
                                       attention_mask=flat_attention_mask)
        pooled_ph = self._dropout(pooled_ph)
        print ("pooled_ph:",pooled_ph.size())
        pooled_ph  = pooled_ph.view(-1,input_ids.size(2),pooled_ph.size(1))
        print ("pooled_ph->",pooled_ph.size())
        # apply weighting layer
        weights = self._weight_layer(pooled_ph)
        weights = weights.view(-1,input_ids.size(2))
        weights = torch.nn.functional.softmax(weights, dim=-1)
        print ("weights:",weights.detach().numpy().tolist())
        print (weights.size())
        # multiply each element by the corresponding scores
        weighted_ph = pooled_ph * weights.unsqueeze(-1)

        if debug:
            print(f"input_ids.size() = {input_ids.size()}")
            print(f"token_type_ids.size() = {token_type_ids.size()}")
            print(f"pooled_ph.size() = {pooled_ph.size()}")
            print(f"weighted_ph.size() = {weighted_ph.size()}")

        if debug:
            print(f"weighted_ph.size() = {weighted_ph.size()}")
        weighted_ph = torch.sum(weighted_ph,1)
        if debug:
            print(f"weighted_ph.size() = {weighted_ph.size()}")

        #apply classification layer
        logits = self._classification_layer(weighted_ph)
        print("weighted:",weighted_ph.size())
        print ("logits:",logits.size())

        if debug:
            print(f"logits.size() = {logits.size()}")

        # shape: batch_size,num_choices
        reshaped_logits = logits.view(-1, input_ids.size(1))
        if debug:
            print(f"reshaped_logits = {reshaped_logits.size()}")
            print(f"labels = {labels.size()}")


        outputs = (reshaped_logits,)

        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(reshaped_logits, labels)
            outputs = (loss,) + outputs

        return outputs, attn  # (loss, reshaped_logits, prob)



