from turtle import forward
import numpy as np
import math
import torch.nn.functional as F
from unicodedata import bidirectional
import torch
from transformers import AutoTokenizer, AutoModel
import torch.nn as nn


class Config:
    '''模型参数配置'''
    def __init__(self):
        self.model_name = 'CodeBert_Blstm'
        self.save_path = './save_dict/' + self.model_name + '.ckpt'  # 保存模型训练结果
        self.device = torch.device('cuda' if torch.cuda.is_available else 'cpu')

        self.dropout = 0.5  #随机失活
        self.num_classes = 2  #类别数
        self.n_vocab = 0  #词汇数，训练时赋值
        self.num_epochs = 20  #训练次数，50轮收敛
        self.batch_size = 16  #mini_batch大小
        self.pad_size = 512  #每句话处理的长度大小（截取或填补）
        self.learning_rate = 2e-5  #学习率 0.0001
        self.cb_embed = 768
        self.embed = 300  #词向量维度，使用了预训练的词向量则维度一致
        self.hidden_size = 256  #LSTM隐藏层
        self.num_layers = 2  #LSTM层数
    

class CodeBert_Blstm(nn.Module):
    def __init__(self, config):
        super(CodeBert_Blstm, self).__init__()
        self.codebert = AutoModel.from_pretrained("microsoft/codebert-base")  # 处理源代码序列
        self.embedding = nn.Embedding(config.n_vocab, config.embed, padding_idx=0)  # 处理pdg序列
        self.lstm = nn.GRU(config.embed, config.hidden_size, config.num_layers, 
                            bidirectional=True, batch_first=True, dropout=config.dropout)  # 训练pdg和ast、ddg、cdg序列

        # 从lstm中得到输出后，将out输入到以下三个Linear层中得到Q、K、V
        self.W_Q = nn.Linear(config.hidden_size*2, config.hidden_size*2, bias=False)
        self.W_K = nn.Linear(config.hidden_size*2, config.hidden_size*2, bias=False)
        self.W_V = nn.Linear(config.hidden_size*2, config.hidden_size*2, bias=False)

        self.linear0 = nn.Sequential(
                                    nn.Linear(config.cb_embed, config.hidden_size*2),
                                    nn.ReLU(),
                                    nn.MaxPool1d(2, stride=2),
                                    nn.Linear(config.hidden_size, config.hidden_size),
                                    nn.ReLU()
                                    )
        self.linear1 = nn.Sequential(
                                    nn.MaxPool1d(2, stride=2),
                                    nn.Linear(config.hidden_size, config.hidden_size),
                                    nn.ReLU()
                                    )
        self.linear2 = nn.Sequential(
                                    # nn.MaxPool1d(2, stride=2),
                                    nn.Linear(config.hidden_size, 128),
                                    nn.ReLU(),
                                    # nn.MaxPool1d(2, stride=2),
                                    nn.Linear(128, 64),
                                    nn.ReLU(),
                                    nn.Linear(64, config.num_classes))
    
    # 加入自注意力机制
    def sf_attention(self, input):
        Q = self.W_Q(input)
        K = self.W_K(input)
        V = self.W_V(input)
        d_k = K.size(-1)
        scores = torch.matmul(Q, K.transpose(1,2)) / math.sqrt(d_k)
        alpha_n = F.softmax(scores, dim=-1)
        code_context = torch.matmul(alpha_n, V)

        output = code_context.sum(1)
        return output, alpha_n

    def forward(self, s, x1, x2):
        s_code = s
        codebert_out = self.codebert(s_code)[0]
        codebert_out = codebert_out[:, 0, :]
        codebert_out = self.linear0(codebert_out)

        code1 = x1  # [batch_size,seq_len]
        out1 = self.embedding(code1)  # [batch_size,seq_len,embedding_size]
        # print(out1.shape)
        out1, _ = self.lstm(out1)  # [batch_size,selq_len,hidden_size*2]
        sf_atten_out1, _ = self.sf_attention(out1)
        # print(sf_atten_out1.shape)
        # print(sf_score.shape)
        # print(sf_score[0][9])
        sf_atten_out1 = self.linear1(sf_atten_out1)

        code2 = x2
        out2, _ =self.lstm(code2)
        sf_atten_out2, _ = self.sf_attention(out2)
        sf_atten_out2 = self.linear1(sf_atten_out2)

        # out = torch.cat([codebert_out, sf_atten_out1, sf_atten_out2], 1)
        # out = codebert_out
        # out = sf_atten_out1
        out = sf_atten_out2
        out = self.linear2(out)
        return out
