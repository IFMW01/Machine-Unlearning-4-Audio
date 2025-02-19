import torch
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
import torchaudio
import os
import librosa
import numpy as np
import torchvision
import random
import torchvision.datasets as cifar_datasets
import torchvision.transforms as transforms
from datasets_unlearn import ravdess
from datasets_unlearn  import audioMNIST
from datasets_unlearn  import speech_commands
from datasets_unlearn import urbansound8k
import utils

from torch.utils.data import DataLoader
from torch.utils.data import Dataset

def seed_worker(worker_id):
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)

def load_datasets(dataset_pointer :str,pipeline:str,unlearnng:bool):
    global labels
    if pipeline == 'mel':
        pipeline_on_wav = WavToMel()
    elif pipeline =='spec':
        pipeline_on_wav = WavToSpec()
    if not os.path.exists(dataset_pointer):
            print(f"Downloading: {dataset_pointer}")
    if dataset_pointer == 'SpeechCommands':
        train_set,test_set = speech_commands.create_speechcommands(pipeline,pipeline_on_wav,dataset_pointer)
        labels = np.load('./labels/speech_commands_labels.npy')
    elif dataset_pointer == 'audioMNIST':
        train_set, test_set = audioMNIST.create_audioMNIST(pipeline,pipeline_on_wav,dataset_pointer)
        labels = np.load('./labels/audiomnist_labels.npy')
    elif dataset_pointer == 'Ravdess':
        train_set, test_set = ravdess.create_ravdess(pipeline,pipeline_on_wav,dataset_pointer)
        labels = np.load('./labels/ravdess_label.npy')
    elif dataset_pointer == 'UrbanSound8K':
        train_set, test_set = urbansound8k.create_UrbanSound8K(pipeline,pipeline_on_wav,dataset_pointer)
        labels = np.load('./labels/ravdess_label.npy')
    elif dataset_pointer =="CIFAR10":
        base_transformations = transforms.Compose(
            [transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
            ]
        )
        train_set =  cifar_datasets.CIFAR10(
            root ='./',
            train=True,
            download=True,
            transform= base_transformations,
        )

        test_set = cifar_datasets.CIFAR10(
            root ='./',
            train=False,
            download=True,
            transform=base_transformations,
        )
    elif dataset_pointer =="CIFAR100":
        base_transformations = transforms.Compose(
            [transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
            ]
        )
        train_set =  cifar_datasets.CIFAR100(
            root ='./',
            train=True,
            download=True,
            transform= base_transformations,
        )

        test_set = cifar_datasets.CIFAR100(
            root ='./',
            train=False,
            download=True,
            transform=base_transformations,
        )

    else:
        raise Exception("Enter valid dataset pointer: e.g. SpeechCommands,audioMNIST,UrbanSound8K,CIFAR10")
        
    if unlearnng:
        return train_set,test_set
    device  = utils.get_device()
    if dataset_pointer == 'SpeechCommands' or dataset_pointer == 'audioMNIST' or dataset_pointer == 'Ravdess' or dataset_pointer == 'UrbanSound8K':
        labels = labels.tolist()
        train_set = DatasetProcessor(train_set,device)
        test_set = DatasetProcessor(test_set,device)
        
    generator = torch.Generator()
    generator.manual_seed(0)
    train_loader = DataLoader(train_set, batch_size=256,shuffle=True,worker_init_fn=seed_worker,
        generator=generator)
    train_eval_loader = DataLoader(train_set, batch_size=256,shuffle=False,worker_init_fn=seed_worker,
        generator=generator)
    test_loader = DataLoader(test_set, batch_size=256,shuffle=False,worker_init_fn=seed_worker,
        generator=generator)
        
    return train_loader,train_eval_loader,test_loader

class DatasetProcessor(Dataset):
  def __init__(self, annotations, device):
    self.audio_files = annotations
    self.features = [] 
    self.labels = [] 
    for idx, path in enumerate(self.audio_files):
       d = torch.load(path)
       d["feature"] = d["feature"][None,:,:]
       self.features.append(d["feature"].to(device))
       self.labels.append(d["label"].to(device))

  def __len__(self):
    return len(self.audio_files)
  
  def __getitem__(self, idx):
    return self.features[idx], self.labels[idx]

class DatasetProcessor_randl(Dataset):
  def __init__(self, annotations,device,num_classes):
    self.audio_files = annotations
    self.features = []
    self.labels = [] 
    for idx, path in enumerate(self.audio_files):
       d = torch.load(path)
       d["feature"] = d["feature"][None,:,:]
       self.features.append(d["feature"].to(device))
       new_label = d["label"] 
       while new_label == d["label"]:
            new_label = random.randint(0, (num_classes-1))
       new_label = torch.tensor(new_label).to(device)
       self.labels.append(new_label)

  def __len__(self):
    return len(self.audio_files)
  
  def __getitem__(self, idx):
    return self.features[idx], self.labels[idx] 

class WavToMel(torch.nn.Module):
    def __init__(
        self,
        input_freq=16000,
        n_fft=512,
        n_mel=32
    ):
        super().__init__()

        self.spec = torchaudio.transforms.Spectrogram(n_fft=n_fft, power=2)

        self.mel_scale = torchaudio.transforms.MelScale(
            n_mels=n_mel, sample_rate=input_freq, n_stft=n_fft // 2 + 1)

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        spec = self.spec(waveform)

        mel = self.mel_scale(spec)

        return mel
    
class WavToSpec(torch.nn.Module):
    def __init__(
        self,
        input_freq=16000,
        n_fft=512,
        n_mel=32
    ):
        super().__init__()

        self.spec = torchaudio.transforms.Spectrogram(n_fft=n_fft, power=2)
        self.mel_scale = torchaudio.transforms.MelScale(
            n_mels=n_mel, sample_rate=input_freq, n_stft=n_fft // 2 + 1)

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        spec = self.spec(waveform)
        spec = torch.from_numpy(librosa.power_to_db(spec))
        return spec

class DatasetProcessor_randl_cifar(Dataset):
  def __init__(self, dataset,device,num_classes):
    self.dataset = dataset
    self.data = []
    self.labels = []
    for inx, (data, label) in enumerate(dataset):
        self.data.append(data.to(device))
        new_label = label
        while new_label == label:
                new_label = random.randint(0, (num_classes-1))
        new_label = torch.tensor(new_label).to(device)
        self.labels.append(new_label)

  def __len__(self):
    return len(self.dataset)
  
  def __getitem__(self, idx):
    return self.data[idx], self.labels[idx] 





