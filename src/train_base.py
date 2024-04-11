import torch
import json
import os
import training as tr
import load_datasets as ld
import utils 

from vgg import VGGish,VGG9
# from transformer import SimpleViT

def create_base_model(model,optimizer,criterion,save_path,device,n_epochs,seed,train_loader,test_loader,results_dict,n_classes):
        best_model,train_accuracy,train_loss,train_ece,test_acc,test_loss,test_ece= tr.train(model,train_loader,test_loader,optimizer,criterion,device,n_epochs,n_classes,seed)
        torch.save(best_model,f"{save_path}Model_{test_acc:.5f}_{test_loss:.5f}.pth")
        df_softmax_outputs = utils.logits(best_model,train_loader,test_loader,device)
        df_softmax_outputs.to_csv(f'{save_path}softmax_outputs.csv',index = False)
        results_dict[f'{seed}'] = [train_accuracy,train_loss,train_ece,test_acc,test_loss,test_ece]
        return results_dict


def main(config):
    dataset_pointer = config.get("dataset_pointer",None)
    pipeline = config.get("pipeline",None)
    architecture = config.get("architecture",None)
    n_epochs = config.get("n_epochs",None)
    seeds = config.get("seeds",None)
    n_classes = config.get("n_classes",None)
    n_inputs = config.get("n_inputs",None)

    print("Received arguments from config file:")
    print(f"Dataset pointer: {dataset_pointer}")
    print(f"Pipeline: {pipeline}")
    print(f"Architecture: {architecture}")
    print(f"Number of epochs: {n_epochs}")
    print(f"Seeds: {seeds}")

    device = utils.get_device()
    results_dict = {}


    train_loader,test_loader = ld.load_datasets(dataset_pointer,pipeline,False)
    for seed in seeds:
        save_dir = f"TRAIN/{dataset_pointer}/{architecture}/{seed}"
        utils.set_seed(seed)
        model,optimizer,scheduler,criterion = utils.initialise_model(architecture,n_inputs,n_classes,device)
        utils.create_dir(save_dir)
        print(save_dir)
        save_path = save_dir + '/'
        results_dict = create_base_model(model,optimizer,criterion,save_path,device,n_epochs,seed,train_loader,test_loader,results_dict,n_classes)
    print(f'Final of all trained models: {results_dict}')
    with open(f"TRAIN/{dataset_pointer}/{architecture}/model_results.json",'w') as f:
        json.dump(results_dict,f)
    print("FIN")

if __name__ == "__main__":
    with open("./configs/base_config.json","r") as f:
        config = json.load(f)
    main(config)