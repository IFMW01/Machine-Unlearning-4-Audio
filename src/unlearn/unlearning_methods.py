import torch
import torch.nn as nn
import torch.optim as optim
import random
import utils
import numpy as np
import Trainer
import scipy.stats as stats
import torch.nn.utils.prune as prune
import time
from Trainer import Trainer
from unlearn.Unlearner import Unlearner
from torch.nn.utils import parameters_to_vector as Params2Vec
from torch.nn.utils import vector_to_parameters as VectorToParams
from torch.nn.utils.prune import _validate_pruning_amount, _validate_pruning_amount_init, _compute_nparams_toprune

# Creates the forget and remain set for random Item Removal, ensuring that d forget is removed from d remain
def create_forget_remain_set(dataset_pointer,forget_instances_num,train_set,seed=42):
    utils.set_seed(seed)
    forget_set = []
    remain_set = train_set
    print(len(remain_set))
    print(type(remain_set))
    forget_set = np.random.choice(remain_set,forget_instances_num, replace=False) 
    remain_set = list(set(remain_set) - set(forget_set))
    return remain_set,forget_set

# Creates the forget and remain set for random Class Removal, ensuring that d forget is removed from d remain
def class_removal(dataset_pointer,forget_classes_num,num_classes,train_set,test_set,seed=42):
    utils.set_seed(seed)
    forget_set = []
    remain_set = train_set

    test_remove = []
    test_keep = test_set

    classes_to_forget = random.sample(range(num_classes), forget_classes_num)
    for i in range(len(remain_set)):
        if torch.load(remain_set[i])['label'] in classes_to_forget:
            forget_set.append(remain_set[i])

    remain_set = list(set(remain_set) - set(forget_set))
            
    for i in range(len(test_keep)):
        if torch.load(test_keep[i])['label'] in classes_to_forget:
            test_remove.append(test_keep[i])

    test_keep = list(set(test_keep) - set(test_remove))
    
    return forget_set,remain_set,test_keep

# Gets accuracy for a model on the forget, remian and test set
def evaluate_forget_remain_test(model,forget_eval_loader,remain_eval_loader,test_loader,device):
    forget_set_acc = utils.evaluate(model,forget_eval_loader,device)
    print(f"Forget set Accuracy: {forget_set_acc:.2f}%")
    remain_set_acc = utils.evaluate(model,remain_eval_loader,device)
    print(f"Remain set Accuracy: {remain_set_acc:.2f}%")
    test_set_acc = utils.evaluate(model,test_loader,device)
    print(f"Test set Accuracy: {test_set_acc:.2f}")

# Loads a model provided a path and returns an optimizer and criterion
def load_model(path,architecture,lr,device):
    model = torch.load(path)
    model.to(device)
    optimizer = optim.SGD(model.parameters(),lr=lr,momentum=0.9)
    criterion = torch.nn.CrossEntropyLoss()
    return model,optimizer,criterion

# Accuracy evaluation
def acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece):
    print(f"Forget accuracy:{forget_accuracy:.2f}%\tForget loss:{forget_loss:.2f}\tForget ECE:{forget_ece:.2f}")
    print(f"Remain accuracy:{remain_accuracy:.2f}%\tRemain loss:{remain_loss:.2f}\tRemain ECE:{remain_ece:.2f}")
    print(f"Test accuracy:{test_accuracy:.2f}%\tTest loss:{test_loss:.2f}\tTest ECE:{test_ece:.2f}")

# Updates results dictionary
def add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time):
    dict['Remain accuracy'] = remain_accuracy
    dict['Remain loss'] = remain_loss
    dict['Remain ece'] = remain_ece
    dict['Test accuracy'] = test_accuracy
    dict['Test loss'] = test_loss
    dict['Test ece'] = test_ece
    dict['Forget accuracy'] = forget_accuracy
    dict['Forget loss'] = forget_loss
    dict['Forget ece'] = forget_ece
    dict['Best epoch'] = best_epoch
    dict['Impair Time'] = impair_time
    dict['Repair Time'] = fine_tune_time
    
    return dict


# NAIVE  UNLEARNING
def naive_unlearning(architecture,n_inputs,n_classes,device,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,n_epochs,dict,seed):
    impair_time = 0.0
    print("\nNaive Unlearning:")
    print("\n")
    utils.set_seed(seed)
    naive_model,optimizer_nu,criterion = utils.initialise_model(architecture,n_inputs,n_classes,device)
    train_naive = Trainer(naive_model, remain_loader, remain_eval_loader, test_loader, optimizer_nu, criterion, device, n_epochs,n_classes,seed)
    naive_model,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,best_epoch,fine_tune_time = train_naive.train()
    forget_accuracy,forget_loss,forget_ece = train_naive.evaluate(forget_eval_loader)
    acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
    dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
    return naive_model,dict


# GRADIENT ASCENT UNLEARNING

def gradient_ascent(path,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,device,n_epoch_impair,n_epoch_repair,dict,n_classes,forget_instances_num,dataset_pointer,architecture,seed):
    print("\nGradient Ascent Unlearning:")
    print("\n")
    utils.set_seed(seed)
    ga_model,optimizer_ga,criterion = load_model(path,architecture,(0.01*(256/forget_instances_num)),device)
    evaluate_forget_remain_test(ga_model,forget_eval_loader,remain_eval_loader,test_loader,device)
    ga_train = Unlearner(ga_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_ga, criterion, device,n_epoch_impair,n_epoch_repair,n_classes,seed)
    ga_model,impair_time = ga_train.gradient_ascent()

    print("\nFine tuning gradient ascent model:")
    optimizer_ft,criterion = utils.set_hyperparameters(ga_model,architecture,lr=0.01)
    ga_fine_tune = Unlearner(ga_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_ft, criterion, device,n_epoch_impair,n_epoch_repair,n_classes,seed)
    ga_model, remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss, test_ece,best_epoch,fine_tune_time= ga_fine_tune.fine_tune()
    forget_accuracy,forget_loss,forget_ece = ga_fine_tune.evaluate(forget_eval_loader)
    acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
    dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
    return ga_model,dict

# FINE TUNE UNLEARNING

def fine_tuning_unlearning(path,device,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,n_epochs,dict,n_classes,architecture,seed):
   print("\nFine Tuning Unlearning:")
   utils.set_seed(seed)
   impair_time = 0.0
   ft_model,optimizer_ft,criterion = load_model(path,architecture,0.01,device)
   ft_train = Unlearner(ft_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_ft, criterion, device,0,n_epochs,n_classes,seed)
   ft_model,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,best_epoch,fine_tune_time = ft_train.fine_tune()
   forget_accuracy,forget_loss,forget_ece= ft_train.evaluate(forget_eval_loader)
   acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
   dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
   return ft_model,dict


# STOCHASTIC TEACHER UNLEARNING

def train_knowledge_distillation(optimizer,criterion,teacher,student,train_loader,epochs,T,soft_target_loss_weight,ce_loss_weight,device):
    teacher.eval()  # Teacher set to evaluation mode
    student.train() # Student to train mode
    teacher.to(device)
    student.to(device)
    impair_time = 0
    train_time = 0
    for epoch in range(epochs):
        running_loss = 0.0
        start_time = time.time()
        epoch_time = 0
        for inputs,labels in train_loader:
            inputs,labels = inputs.to(device),labels.to(device)

            optimizer.zero_grad()

            # Forward pass with the teacher model - do not save gradients here as we do not change the teacher's weights
            with torch.no_grad():
                teacher_logits = teacher(inputs)

            # Forward pass with the student model
            student_logits = student(inputs)
            #Soften the student logits by applying softmax first and log() second
            soft_targets = nn.functional.softmax(teacher_logits / T,dim=-1)
            soft_prob = nn.functional.log_softmax(student_logits / T,dim=-1)
            # Calculate the soft targets loss. Scaled by T**2 as suggested by the authors of the paper "Distilling the knowledge in a neural network"
            soft_targets_loss = torch.sum(soft_targets * (soft_targets.log() - soft_prob)) / soft_prob.size()[0] * (T**2)
            # Calculate the true label loss
            label_loss = criterion(student_logits,labels)
            teacher_loss =  criterion(teacher_logits,labels)
            loss = soft_target_loss_weight * soft_targets_loss + ce_loss_weight * label_loss
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            end_time = time.time()
            epoch_time = end_time - start_time
            train_time += round(epoch_time,3)
        print(f"Epoch {epoch+1}/{epochs},Loss: {running_loss / len(train_loader)}")
    return student,train_time

def stochastic_teacher_unlearning(path,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,device,n_inputs,n_classes,architecture,dict,n_impair_epochs,n_repair_epochs,seed):
  print("\nStochastic Teacher Unlearning:")
  print("\n")
  utils.set_seed(seed)
  kd_bad_lr  = 0.01
      
  student_model,bad_optimizer,criterion,= load_model(path,architecture,kd_bad_lr,device)

  stochastic_teacher,stochastic_teacher_optimizer,stochastic_teacher_criterion= utils.initialise_model(architecture,n_inputs,n_classes,device,seed)
  evaluate_forget_remain_test(student_model,forget_eval_loader,remain_eval_loader,test_loader,device)

  student_model,impair_time =  train_knowledge_distillation(bad_optimizer,criterion,teacher=stochastic_teacher,student=student_model,train_loader=forget_loader,epochs=n_impair_epochs,T=1,soft_target_loss_weight=1.0,ce_loss_weight=0,device=device)
  print("Stochastic teacher knowledge distillation complete")
  evaluate_forget_remain_test(student_model,forget_eval_loader,remain_eval_loader,test_loader,device)
  optimizer_gt,criterion_gt = utils.set_hyperparameters(student_model,architecture,0.01)  
  gt_model,optimizer_nn,criterion,= load_model(path,architecture,0.5,device) 
  student_model,fine_tune_time = train_knowledge_distillation(optimizer_gt,criterion_gt,teacher=gt_model,student=student_model,train_loader=remain_loader,epochs=n_repair_epochs,T=1,soft_target_loss_weight=1.0,ce_loss_weight=0,device=device)
  print("Good teacher knowledge distillation complete")

  forget_accuracy,forget_loss,forget_ece  = utils.evaluate_test(student_model,forget_eval_loader,criterion,n_classes,device)
  remain_accuracy,remain_loss,remain_ece = utils.evaluate_test(student_model,remain_eval_loader,criterion,n_classes,device)
  test_accuracy,test_loss,test_ece = utils.evaluate_test(student_model,test_loader,criterion,n_classes,device)
  acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
 
  dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,n_repair_epochs,impair_time,fine_tune_time)
  return student_model,dict

  # ONE-SHOT MAGNITUTE UNLEARNING
  
def omp_unlearning(path,device,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,pruning_ratio,n_epochs,dict,n_classes,architecture,seed):
    print("\nOMP Unlearning:")
    print("\n")
    utils.set_seed(seed)
    omp_model,opimizer,criterion,= load_model(path,architecture,0.01,device)
    start_time = time.time()
    omp_model = global_prune_with_masks(omp_model,pruning_ratio)
    end_time = time.time()
    impair_time = round((end_time -start_time),3)

    optimizer_omp,criterion = utils.set_hyperparameters(omp_model,architecture,lr=0.01)
    print("Pruning Complete:")
    evaluate_forget_remain_test(omp_model,forget_eval_loader,remain_eval_loader,test_loader,device)
    print("\nFine tuning pruned model:")
    omp_train = Unlearner(omp_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_omp, criterion, device,0,n_epochs,n_classes,seed)
    omp_model,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss, test_ece,best_epoch,fine_tune_time= omp_train.fine_tune()
    forget_accuracy,forget_loss,forget_ece = omp_train.evaluate(forget_eval_loader)
    acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
    dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
    return omp_model,dict

# CONSINE OMP PRUNE UNLEARNING


def cosine_unlearning(path,device,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,n_repair,dict,n_classes,architecture,seed):
    print("\nConsine Unlearning:")
    print("\n")
    prune_rate = torch.linspace(0,1,101)
    cosine_sim = []

    base_model,optimizer,criterion,= load_model(path,architecture,0.01,device)
    start_time = time.time()
    base_vec = vectorise_model(base_model)
    evaluate_forget_remain_test(base_model,forget_eval_loader,remain_eval_loader,test_loader,device)
    for pruning_ratio in prune_rate:
        pruning_ratio = float(pruning_ratio)
        prune_model,optimizer,criterion,= load_model(path,architecture,0.01,device)
        prune_model = global_prune_without_masks(prune_model,pruning_ratio)
        prune_model_vec = vectorise_model(prune_model)
        cosine_sim.append(cosine_similarity(base_vec, prune_model_vec).item())
 
    c = torch.vstack((torch.Tensor(cosine_sim), prune_rate))
    d = c.T
    dists = []
    for i in d:
        dists.append(torch.dist(i, torch.Tensor([1, 1])))
    min = torch.argmin(torch.Tensor(dists))

    consine_model = global_prune_without_masks(base_model, float(prune_rate[min]))
    end_time = time.time()
    impair_time = round((end_time - start_time),3)

    print(f"Percentage Prune: {prune_rate[min]:.2f}")
    evaluate_forget_remain_test(consine_model,forget_loader,remain_eval_loader,test_loader,device)
    print("\nFine tuning cosine model:")
    optimizer_cosine,criterion = utils.set_hyperparameters(consine_model,architecture,lr=0.01)
    cosine_train = Unlearner(consine_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_cosine, criterion, device,0,5,n_classes,seed)
    consine_model,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss, test_ece,best_epoch,fine_tune_time= cosine_train.fine_tune()
    forget_accuracy,forget_loss,forget_ece = cosine_train.evaluate(forget_eval_loader)
    acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
    dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
    return consine_model,dict

def pop_unlearning(path,device,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,n_repair,dict,n_classes,architecture,seed):
    print("\n POP Unlearning:")
    print("\n")
    prune_rate = torch.linspace(0,1,101)
    cosine_sim = []

    base_model,optimizer,criterion,= load_model(path,architecture,0.01,device)
    start_time = time.time()
    base_vec = vectorise_model(base_model)
    evaluate_forget_remain_test(base_model,forget_eval_loader,remain_eval_loader,test_loader,device)
    for pruning_ratio in prune_rate:
        pruning_ratio = float(pruning_ratio)
        prune_model,optimizer,criterion,= load_model(path,architecture,0.01,device)
        prune_model = global_prune_without_masks(prune_model,pruning_ratio)
        prune_model_vec = vectorise_model(prune_model)
        cosine_sim.append(cosine_similarity(base_vec, prune_model_vec).item())
 
    c = torch.vstack((torch.Tensor(cosine_sim), prune_rate))
    d = c.T
    dists = []
    for i in d:
        dists.append(torch.dist(i, torch.Tensor([1, 1])))
    min = torch.argmin(torch.Tensor(dists))

    unsafe_prune = prune_rate[min]+0.1
    if unsafe_prune>=0.96:
        unsafe_prune = 0.95
    
    pop_model = global_prune_without_masks(base_model, float(unsafe_prune))
    end_time = time.time()
    pre_train = vectorise_model(pop_model).count_nonzero()
    print(f'Number of parameters pre training: {pre_train}')
    impair_time = round((end_time-start_time),3)
    print(f"Percentage Prune: {unsafe_prune:.2f}")

    print(f"\nModel accuracies post POP:")
    evaluate_forget_remain_test(pop_model,forget_loader,remain_eval_loader,test_loader,device)
    print("\nFine tuning POP model:")
    optimizer_cosine,criterion = utils.set_hyperparameters(pop_model,architecture,lr=0.01)
    kk_train = Unlearner(pop_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_cosine, criterion, device,0,5,n_classes,seed)
    pop_model,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss, test_ece,best_epoch,fine_tune_time= kk_train.fine_tune()
    post_train = vectorise_model(pop_model).count_nonzero()
    print(f'Number of parameters post training: {post_train}')
    forget_accuracy,forget_loss,forget_ece = kk_train.evaluate(forget_eval_loader)
    acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
    dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
    return pop_model,dict

# Amnesiac Unlearning - Know as "Unlearning" from Amnesiac Machine Learning paper

def amnesiac_unlearning(path,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,forget_rand_lables_loader,device,n_epoch_impair,n_epoch_repair,dict,n_classes,architecture,seed):
    print("\nAmnesiac Unlearning:")
    print("\n")
    # add lr
    amnesiac_model,optimizer_ft,criterion = load_model(path,architecture,0.001,device)
    print("\n Orignial model accuracy:")
    evaluate_forget_remain_test(amnesiac_model,forget_eval_loader,remain_eval_loader,test_loader,device)
    randl_train = Unlearner(amnesiac_model,remain_loader, remain_eval_loader, forget_rand_lables_loader,forget_eval_loader,test_loader, optimizer_ft, criterion, device,n_epoch_impair,n_epoch_repair,n_classes,seed)
    amnesiac_model,impair_time=  randl_train.amnesiac()
    print("Performed Amnesiac Unlearning")
    evaluate_forget_remain_test(amnesiac_model,forget_eval_loader,remain_eval_loader,test_loader,device)

    print("\nFine tuning amnesiac model:")
    optimizer_ft,criterion = utils.set_hyperparameters(amnesiac_model,architecture,lr=0.01)
    randl_fine_tune = Unlearner(amnesiac_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_ft, criterion, device,n_epoch_impair,n_epoch_repair,n_classes,seed)
    amnesiac_model, remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss, test_ece,best_epoch,fine_tune_time= randl_fine_tune.fine_tune()
    forget_accuracy,forget_loss,forget_ece = randl_fine_tune.evaluate(forget_eval_loader)
    
    acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
    dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
    return amnesiac_model,dict

# LABEL SMOOTHING UNLEARNING

def label_smoothing_unlearning(path,device,remain_loader,remain_eval_loader,test_loader,forget_loader,forget_eval_loader,n_epoch_impair,n_epoch_repair,dict,n_classes,forget_instances_num,architecture,seed):
   print("\n Label Smoothing Unlearning:")
   utils.set_seed(seed)
   ls_model,optimizer,criterion = load_model(path,architecture,(0.01*(256/forget_instances_num)),device)
   criterion_ls = nn.CrossEntropyLoss(label_smoothing=1)
   ls_train = Trainer(ls_model, forget_loader, forget_eval_loader, test_loader, optimizer, criterion_ls, device, n_epoch_impair,n_classes,seed)
   ls_model,forget_accuracy,forget_loss,forget_ece,test_accuracy,test_loss,test_ece,best_epoch,impair_time = ls_train.train()
   print(f"\nModel accuracies post label smoothing:")
   evaluate_forget_remain_test(ls_model,forget_eval_loader,remain_eval_loader,test_loader,device)

   print(f"\nFine Tuning:")
   optimizer_ft,criterion = utils.set_hyperparameters(ls_model,architecture,lr=0.01)
   ls_fine_tune = Unlearner(ls_model,remain_loader, remain_eval_loader, forget_loader,forget_eval_loader,test_loader, optimizer_ft, criterion, device,n_epoch_impair,n_epoch_repair,n_classes,seed)
   ls_model, remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss, test_ece,best_epoch,fine_tune_time= ls_fine_tune.fine_tune()
   forget_accuracy,forget_loss,forget_ece = ls_fine_tune.evaluate(forget_eval_loader)

   acc_scores(forget_accuracy,forget_loss,forget_ece,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece)
   dict =  add_data(dict,remain_accuracy,remain_loss,remain_ece,test_accuracy,test_loss,test_ece,forget_accuracy,forget_loss,forget_ece,best_epoch,impair_time,fine_tune_time)
   return ls_model,dict

def vectorise_model(model):
    return Params2Vec(model.parameters())

def cosine_similarity(base_weights, model_weights):
    return torch.nan_to_num(torch.clip(torch.dot(
        base_weights, model_weights
    ) / (
        torch.linalg.norm(base_weights)
        * torch.linalg.norm(model_weights)
    ),-1, 1),0)

# Removing masks from pruned model
def global_prune_without_masks(model, amount):
    parameters_to_prune = []
    for mod in model.modules():
        if hasattr(mod, "weight"):
            if isinstance(mod.weight, torch.nn.Parameter):
                parameters_to_prune.append((mod, "weight"))
        if hasattr(mod, "bias"):
            if isinstance(mod.bias, torch.nn.Parameter):
                parameters_to_prune.append((mod, "bias"))
    parameters_to_prune = tuple(parameters_to_prune)
    prune.global_unstructured(
        parameters_to_prune,
        pruning_method=prune.L1Unstructured,
        amount=amount,
    )
    for mod in model.modules():
        if hasattr(mod, "weight_orig"):
            if isinstance(mod.weight_orig, torch.nn.Parameter):
                prune.remove(mod, "weight")
        if hasattr(mod, "bias_orig"):
            if isinstance(mod.bias_orig, torch.nn.Parameter):
                prune.remove(mod, "bias")
    return model

# Standard OMP with masks
def global_prune_with_masks(model, amount):
    parameters_to_prune = []
    for mod in model.modules():
        if hasattr(mod, "weight"):
            if isinstance(mod.weight, torch.nn.Parameter):
                parameters_to_prune.append((mod, "weight"))
        if hasattr(mod, "bias"):
            if isinstance(mod.bias, torch.nn.Parameter):
                parameters_to_prune.append((mod, "bias"))
    parameters_to_prune = tuple(parameters_to_prune)
    prune.global_unstructured(
        parameters_to_prune,
        pruning_method=prune.L1Unstructured,
        amount=amount,
    )
    return model







