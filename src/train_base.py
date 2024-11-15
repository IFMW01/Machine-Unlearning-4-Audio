import torch
import json
import Trainer 
from Trainer import Trainer
from datasets_unlearn import load_datasets as ld
import utils 

#Train base models for seeds proivded in the config automatically and save the resulting model along with saving loss outputs for train and test set
 
def create_base_model(train,save_model_path,save_mia_path,device,seed,train_loader,test_loader,results_dict):
    results_dict[f'{seed}'] = {}
    best_model,train_accuracy,train_loss,train_ece,test_acc,test_loss,test_ece,best_epoch,best_time= train.train()
    torch.save(best_model,f"{save_model_path}Model_{test_acc:.5f}_{test_loss:.5f}.pth")
    df_loss_outputs = utils.logits(best_model,train_loader,test_loader,device)
    df_loss_outputs.to_csv(f'{save_model_path}loss_outputs.csv',index = False)
    df_loss_outputs.to_csv(f'{save_mia_path}{seed}_loss_outputs.csv',index = False)
    results_dict[f'{seed}'] = utils.update_dict(results_dict[f'{seed}'],best_time,best_epoch,train_accuracy,train_loss,train_ece,test_acc,test_loss,test_ece)
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
    print(f"Number of classes: {n_classes}")
    print(f"Number of inputs: {n_inputs}")

    device = utils.get_device()
    results_dict = {}

    # Iterates over the provided seeds and creates model 
    train_loader,train_eval_loader,test_loader = ld.load_datasets(dataset_pointer,pipeline,False)
    for seed in seeds:

        save_dir = f"Results/{dataset_pointer}/{architecture}"
        utils.set_seed(seed)
        model,optimizer,criterion = utils.initialise_model(architecture,n_inputs,n_classes,device)
        utils.create_dir(save_dir)
        save_model_path = f'{save_dir}/{seed}/'
        utils.create_dir(save_model_path)
        save_mia_path = f'{save_dir}/MIA/'
        utils.create_dir(save_mia_path)
        train = Trainer(model, train_loader, train_eval_loader, test_loader, optimizer, criterion, device, n_epochs,n_classes,seed)
        results_dict = create_base_model(train,save_model_path,save_mia_path,device,seed,train_loader,test_loader,results_dict)

    print(f'Final of all trained models: {results_dict}')

    with open(f"{save_dir}/training_results.json",'w') as f:

        json.dump(results_dict,f)

    print("FIN")

if __name__ == "__main__":

    with open("./configs/base_config.json","r") as f:

        config = json.load(f)
        
    main(config)