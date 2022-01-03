import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from tqdm import tqdm

from utils.utils_metrics import evaluate


def get_lr(optimizer):
    for param_group in optimizer.param_groups:
        return param_group['lr']

def fit_one_epoch(model_train, model, loss_history, loss, optimizer, epoch, epoch_step, epoch_step_val, gen, gen_val, Epoch, cuda, test_loader, Batch_size, lfw_eval_flag):
    total_triple_loss   = 0
    total_CE_loss       = 0
    total_accuracy      = 0

    val_total_triple_loss   = 0
    val_total_CE_loss       = 0
    val_total_accuracy      = 0

    model_train.train()
    print('Start Train')
    with tqdm(total=epoch_step,desc=f'Epoch {epoch + 1}/{Epoch}',postfix=dict,mininterval=0.3) as pbar:
        for iteration, batch in enumerate(gen):
            if iteration >= epoch_step:
                break
            images, labels = batch
            with torch.no_grad():
                if cuda:
                    images  = torch.from_numpy(images).type(torch.FloatTensor).cuda()
                    labels  = torch.from_numpy(labels).long().cuda()
                else:
                    images  = torch.from_numpy(images).type(torch.FloatTensor)
                    labels  = torch.from_numpy(labels).long()

            optimizer.zero_grad()
            before_normalize, outputs1  = model.forward_feature(images)
            outputs2                    = model.forward_classifier(before_normalize)
            
            _triplet_loss   = loss(outputs1, Batch_size)
            _CE_loss        = nn.NLLLoss()(F.log_softmax(outputs2, dim = -1), labels)
            _loss           = _triplet_loss + _CE_loss

            _loss.backward()
            optimizer.step()        

            with torch.no_grad():
                accuracy         = torch.mean((torch.argmax(F.softmax(outputs2, dim=-1), dim=-1) == labels).type(torch.FloatTensor))
                
            total_triple_loss   += _triplet_loss.item()
            total_CE_loss       += _CE_loss.item()
            total_accuracy      += accuracy.item()

            pbar.set_postfix(**{'total_triple_loss' : total_triple_loss / (iteration + 1), 
                                'total_CE_loss'     : total_CE_loss / (iteration + 1), 
                                'accuracy'          : total_accuracy / (iteration + 1), 
                                'lr'                : get_lr(optimizer)})
            pbar.update(1)
    print('Finish Train')

    model_train.eval()
    print('Start Validation')
    with tqdm(total=epoch_step_val,desc=f'Epoch {epoch + 1}/{Epoch}',postfix=dict,mininterval=0.3) as pbar:
        for iteration, batch in enumerate(gen_val):
            if iteration >= epoch_step_val:
                break
            images, labels = batch
            with torch.no_grad():
                if cuda:
                    images  = torch.from_numpy(images).type(torch.FloatTensor).cuda()
                    labels  = torch.from_numpy(labels).long().cuda()
                else:
                    images  = torch.from_numpy(images).type(torch.FloatTensor)
                    labels  = torch.from_numpy(labels).long()

                optimizer.zero_grad()
                before_normalize, outputs1  = model.forward_feature(images)
                outputs2                    = model.forward_classifier(before_normalize)
                
                _triplet_loss   = loss(outputs1, Batch_size)
                _CE_loss        = nn.NLLLoss()(F.log_softmax(outputs2,dim=-1),labels)
                _loss           = _triplet_loss + _CE_loss

                accuracy        = torch.mean((torch.argmax(F.softmax(outputs2, dim=-1), dim=-1) == labels).type(torch.FloatTensor))
                
                val_total_triple_loss   += _triplet_loss.item()
                val_total_CE_loss       += _CE_loss.item()
                val_total_accuracy      += accuracy.item()

            pbar.set_postfix(**{'val_total_triple_loss' : val_total_triple_loss / (iteration + 1), 
                                'val_total_CE_loss'     : val_total_CE_loss / (iteration + 1), 
                                'val_accuracy'          : val_total_accuracy / (iteration + 1), 
                                'lr'                    : get_lr(optimizer)})
            pbar.update(1)
    print('Finish Validation')

    if lfw_eval_flag:
        print("开始进行LFW数据集的验证。")
        labels, distances = [], []
        for _, (data_a, data_p, label) in enumerate(test_loader):
            with torch.no_grad():
                data_a, data_p = data_a.type(torch.FloatTensor), data_p.type(torch.FloatTensor)
                if cuda:
                    data_a, data_p = data_a.cuda(), data_p.cuda()
                out_a, out_p = model(data_a), model(data_p)
                dists = torch.sqrt(torch.sum((out_a - out_p) ** 2, 1))
            distances.append(dists.data.cpu().numpy())
            labels.append(label.data.cpu().numpy())
        
        labels      = np.array([sublabel for label in labels for sublabel in label])
        distances   = np.array([subdist for dist in distances for subdist in dist])
        _, _, accuracy, _, _, _, _ = evaluate(distances,labels)
        print('LFW_Accuracy: %2.5f+-%2.5f' % (np.mean(accuracy), np.std(accuracy)))

    loss_history.append_loss(total_accuracy / epoch_step, (total_triple_loss + total_CE_loss) / epoch_step, (val_total_triple_loss + val_total_CE_loss) / epoch_step_val)
    
    print('Epoch:'+ str(epoch+1) + '/' + str(Epoch))
    print('Total Loss: %.4f' % ((total_triple_loss + total_CE_loss) / epoch_step))
    torch.save(model.state_dict(), 'logs/Epoch%d-Total_Loss%.4f.pth-Val_Loss%.4f.pth'%((epoch+1),
                                                    (total_triple_loss + total_CE_loss) / epoch_step,
                                                    (val_total_triple_loss + val_total_CE_loss) / epoch_step_val))
    
    return (val_total_triple_loss + val_total_CE_loss) / epoch_step_val
