#loading libraries
import csv
import datetime
from __future__ import print_function
import math
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from sklearn import metrics
import tensorflow as tf
from tensorflow.python.data import Dataset
tf.logging.set_verbosity(tf.logging.ERROR)
pd.options.display.max_rows = 10
pd.options.display.float_format = '{:.1f}'.format

#Importing data and creating features:
db0 = pd.read_csv("DataChallenge2.csv", sep=",")

##Normalizing Price to Log Scale
#def log_normalize(series):
#  return series.apply(lambda x:math.log(x+1.0))
#db0['Price'] = log_normalize(db0['Price'])
#
##Normalizing Price to Linear Scale
#def linear_scale(series):
#  min_val = series.min()
#  max_val = series.max()
#  scale = (max_val - min_val) / 2.0
#  return series.apply(lambda x:((x - min_val) / scale) - 1.0)
#db0['Price'] = linear_scale(db0['Price'])


#One-hot features:
db0 ['Detached'] = (db0['Type']=="D").astype(int)
db0 ['Lease'] = (db0['Free/Lease']=="L").astype(int)
db0 ['New'] = (db0['NewBuild']=="Y").astype(int)
#Area One-hot features:
db0 ['AreaE'] = (db0['Area']=="E").astype(int)
db0 ['AreaN'] = (db0['Area']=="N").astype(int)
db0 ['AreaNW'] = (db0['Area']=="NW").astype(int)
db0 ['AreaSE'] = (db0['Area']=="SE").astype(int)
db0 ['AreaSW'] = (db0['Area']=="SW").astype(int)
#Buckets of Prices:
db0 ['LowPrice'] = (db0['Price']<db0['Price'].quantile(0.02975)).astype(int)
db0 ['HighPrice'] = (db0['Price']>db0['Price'].quantile(.99)).astype(int)
db0 ['MedPrice'] = (
        (db0['Price']>db0['Price'].quantile(0.02975))
        &
        (db0['Price']<db0['Price'].quantile(.99))
        ).astype(int)
#CrossFeatures:
#db0 ['North'] = (db0['AreaN'] | db0['AreaNW']).astype(int)
#db0 ['South'] = (db0['AreaSE'] | db0['AreaSW']).astype(int)
#db0 ['West'] = (db0['AreaSW'] | db0['AreaNW']).astype(int)
#db0 ['East'] = (db0['AreaE'] | db0['AreaSE']).astype(int)
db0 ['NewLease'] = (db0['New'] & db0['Lease']).astype(int)
db0 ['NewFree'] = (db0['New'] & (db0['Free/Lease']=="F")).astype(int)
db0 ['OldLease'] = ((db0['NewBuild']=="N") & db0['Lease']).astype(int)
db0 ['OldFree'] = ((db0['NewBuild']=="N") & 
    (db0['Free/Lease']=="F")).astype(int)

#Randomizing the order of the entries:
db0 = db0.reindex(np.random.permutation(db0.index))
#Segregating Training and Testing data:
db = db0.head(int(0.75*(len(db0))))
dbtest = db0.tail(len(db0)-len(db))

#Defining functions to preprocess and select features and targets:
def preprocess_features(db):
  selected_features = db[
    ['Lease',
     'New',
     'AreaE',
     'AreaN',
     'AreaNW',
     'AreaSE',
     'AreaSW',
     'LowPrice',
     'HighPrice',
     'MedPrice',
     'NewLease',
     'NewFree',
     'OldLease',
     'OldFree',
     ]]
  processed_features = selected_features.copy()
  return processed_features

def preprocess_targets(db):
  output_targets = pd.DataFrame()
  output_targets["Detached"] = db["Detached"].copy()
  return output_targets



#NEW CODE - Undersampling:
#Dividing the set into Training and Validation examples and targets
detacheddb = db[db['Detached']==1]
terracedb = db[db['Detached']==0].head(int(0.35*(len(db))))
oversampledb = pd.concat([detacheddb, terracedb])
db = oversampledb
db = db.reindex(np.random.permutation(db.index))

detacheddb.describe()
terracedb.describe()

dbfinal = oversampledb
print('Detached: ',dbfinal['Detached'].sum())
print('Total: ',len(dbfinal))
print('Balance: ',dbfinal['Detached'].sum()/len(dbfinal))


head75 = int(0.75*(len(db)))
tail25 = len(db)- head75
training_examples = preprocess_features(db.head(head75))
training_targets = preprocess_targets(db.head(head75))
validation_examples = preprocess_features(db.tail(tail25))
validation_targets = preprocess_targets(db.tail(tail25))


#Defining the Feature Columns:
def construct_feature_columns(input_features):
  return set([tf.feature_column.numeric_column(my_feature)
              for my_feature in input_features])

#Defining the input function:
def my_input_fn(features,targets,batch_size=1,shuffle=True,num_epochs=None):
    # Convert pandas data into a dict of np arrays.
    features = {key:np.array(value) for key,value in dict(features).items()}                                           
    # Construct a dataset, and configure batching/repeating.
    ds = Dataset.from_tensor_slices((features,targets)) # warning: 2GB limit
    ds = ds.batch(batch_size).repeat(num_epochs)    
    if shuffle:
      ds = ds.shuffle(buffer_size=10000)    
    # Return the next batch of data.
    features, labels = ds.make_one_shot_iterator().get_next()
    return features, labels

def model_size(estimator):
  variables = estimator.get_variable_names()
  size = 0
  for variable in variables:
    if not any(x in variable 
               for x in ['global_step',
                         'centered_bias_weight',
                         'bias_weight',
                         'Ftrl']
              ):
      size += np.count_nonzero(estimator.get_variable_value(variable))
  return size


#Defining Neural Network Training function:
def train_nn_classifier_model(
    learning_rate,
    steps,
    periods,
    batch_size,
    hidden_units,
    training_examples,
    training_targets,
    validation_examples,
    validation_targets):

  steps_per_period = steps / periods
  
  #Setting optimizer and DNN Regressor function
  my_optimizer = tf.train.GradientDescentOptimizer(learning_rate=learning_rate)
  my_optimizer = tf.contrib.estimator.clip_gradients_by_norm(my_optimizer, 5.0)
  dnn_classifier = tf.estimator.DNNClassifier(
      feature_columns=construct_feature_columns(training_examples),
      hidden_units=hidden_units,
      optimizer=my_optimizer
  )
  
  # Creating input functions:
  training_input_fn = lambda: my_input_fn(
      training_examples, 
      training_targets["Detached"], 
      batch_size=batch_size)
  predict_training_input_fn = lambda: my_input_fn(
      training_examples, 
      training_targets["Detached"], 
      num_epochs=1, 
      shuffle=False)
  predict_validation_input_fn = lambda: my_input_fn(
      validation_examples, validation_targets["Detached"], 
      num_epochs=1, 
      shuffle=False)

  # Training the model inside a loop that periodically assess and print
  # loss metrics:
  print("Training model...")
  print("LogLoss (on training data):")
  training_log_losses = []
  #validation_log_losses = []
  for period in range (0, periods):
    # Train the model, starting from the prior state.
    dnn_classifier.train(
        input_fn=training_input_fn,
        steps=steps_per_period,
    )
    
    # Take a break and compute predictions.
    training_probabilities = dnn_classifier.predict(input_fn=predict_training_input_fn)
    
    training_probabilities = np.array([item['probabilities'] for item in training_probabilities])
        
    validation_probabilities = dnn_classifier.predict(input_fn=predict_validation_input_fn)
    
    validation_probabilities = np.array([item['probabilities'] for item in validation_probabilities])
    
    # Compute training and validation loss:
    training_log_loss = metrics.log_loss(training_targets, training_probabilities)
    #validation_log_loss = metrics.log_loss(validation_targets, validation_probabilities)

    # Occasionally print the current loss:
    print("\n","  ",datetime.datetime.now().time().hour,':',
          datetime.datetime.now().time().minute)
    print("  period %02d" % (period))

    print("  Test LogLoss %0.6f" % (training_log_loss))
    #print("  Validation LogLoss: %0.6f" % (validation_log_loss))
    training_log_losses.append(training_log_loss)
    #validation_log_losses.append(validation_log_loss)
  
  
  # Output a graph of loss metrics over each period:
#  plt.ylabel("LogLoss")
#  plt.xlabel("Periods")
#  plt.title("LogLoss vs. Periods")
#  plt.tight_layout()
#  plt.plot(training_log_losses, label="training")
#  plt.plot(validation_log_losses, label="validation")
#  plt.legend()


  #Printing final results:
  print("Model training finished.")
  print("Final LogLoss (on training data):   %0.6f"
        % training_log_loss)
  #print("Final LogLoss (on validation data): %0.6f" % validation_log_loss)

  return dnn_classifier



#Training the NN model using the Training Function:
dnn_classifier = train_nn_classifier_model(
    learning_rate=0.00002,
    steps=8000,
    periods = 50,
    batch_size= 100,
    hidden_units=[10, 10, 10],
    training_examples=training_examples,
    training_targets=training_targets,
    validation_examples=validation_examples,
    validation_targets=validation_targets)


#Assessing results with a different dataset (segregated at the beginning):
#Preprocessing features and targets and running the input function:
test_examples = preprocess_features(dbtest)
test_targets = preprocess_targets(dbtest)

predict_test_input_fn = lambda: my_input_fn(
      test_examples, 
      test_targets['Detached'], 
      num_epochs=1, 
      shuffle=False)

#Predicting the values and saving them in an Numpy Array:
test_probabilities = dnn_classifier.predict(input_fn=predict_test_input_fn)
test_probabilities = np.array([
        item['probabilities'] for item in test_probabilities])


#Calculating Test Data LogLoss:
test_log_loss = metrics.log_loss(test_targets, test_probabilities)
    
#Transforming the Prediction NpArray as a Dataframe:
testpred0 = test_probabilities.copy()
testpred1 = pd.DataFrame
testpred1 = testpred1(index=test_targets.index.values,
                      columns=["Detached"])
testpred2 = pd.DataFrame
testpred2 = testpred2(data=testpred0, index=test_targets.index.values,columns=["Terrace","Detached"])


#Defining Detached Probabilities as True or False:
threshold = 0.4295
testpred1 ["Detached"]= (testpred2 ["Detached"]>=threshold).astype(int)
print(testpred1 ["Detached"].sum())


#Calculating Model's Metrics:
f1score = 100 * metrics.f1_score(test_targets, testpred1)
accuracy = 100 * metrics.accuracy_score(test_targets, testpred1)
precision = 100 * metrics.precision_score(test_targets, testpred1)
recall = 100 * metrics.recall_score(test_targets, testpred1)
numofpredictions = testpred1['Detached'].sum()

#Printing Final Metrics Results:
print('Results in Test Dataset:')
print('Test Data LogLoss:',  '{:,.3f}'.format(test_log_loss))
print('Predicted Detacheds:',numofpredictions, '\n')

print('Actual Detacheds:',test_targets["Detached"].sum())
print('F1 Score:', '{:,.2f}'.format(f1score), '%')
print('Accuracy:','{:,.2f}'.format(accuracy), '%')
print('Precision:','{:,.2f}'.format(precision), '%')
print('Recall:','{:,.2f}'.format(recall), '%')


"""Out:
Results in Test Dataset:
Test Data RMSE: 0.265
Actual Detacheds: 573
Predicted Detacheds: 164
Actual Terraces: 4658
Predicted Terraces: 5067
F1 Score: 43.96 %
Accuracy: 92.10 %
Precision: 98.78 %
Recall: 28.27 %
"""

