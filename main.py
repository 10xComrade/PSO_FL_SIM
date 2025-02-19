
from measurements.tools.display_output import *
from random import randint , random , sample , seed 
import copy 

# Global parameters

# PSO parameters                            
iw = 0.1                                    # Inertia Weight (Higher => Exploration | Lower => Exploitation)   
c1 = 0.1                                    # Pbest coefficient
c2 = 10                                     # Gbest coefficient
pop_n = 7                                   # Population number
max_iter = 300                              # Maximum iteration
conv = 0.1                                  # Convergence value
global_best = 0.7                           # NOTE : Temporary value , change it later !!!

# System parameters
DEPTH = 4
WIDTH = 3
dimensions = 0 if DEPTH <= 0 or WIDTH <= 0 else sum(WIDTH**i for i in range(DEPTH))   
Client_list = []
Role_buffer = []
Role_dictionary = {}
randomness_seed = 50
tracking_mode = True   
velocity_factor = 0.1                       # Increasing velocity_factor causes more exploration resulting higher fluctuations in the particles plot (default range between 0 and 1 (Guess))

# Graph illustration parameters 
particles_fitness_buffer = []
particles_fitnesses_avg = []
gbest_particle_fitness_results = []
iterations = []
tpd_buffer = []
tpds_avg = []

# Particle class
class Particle :
    def __init__(self, pos , fitness , velocity , best_pos_fitness) : 
        self.pos = pos
        self.fitness = fitness
        self.velocity = velocity
        self.best_pos = self.pos.copy()
        self.best_pos_fitness = best_pos_fitness

# Swarm class
class Swarm : 
    def __init__(self , pop_n , dimensions , root) :
        self.particles = self.__generate_random_particles(pop_n , dimensions , root)
        self.global_best_particle = max(self.particles, key=lambda particle: particle.fitness)

    def __generate_random_particles(self, pop_n, dimensions , root):
        init_particle_pos = [client.client_id for client in Client_list if client.is_aggregator]
        cll = len(Client_list)
        particles = []

        for i in range(pop_n):
            if i != 0 : 
                particle_pos = sample(range(cll), dimensions)
                root = reArrangeHierarchy(particle_pos)  

            else : 
                particle_pos = init_particle_pos

            fitness, _ , _ = processing_fitness(root)
            velocity = [0 for _ in range(dimensions)]       
            best_pos_fitness = fitness                   
            particles.append(Particle(particle_pos, fitness, velocity, best_pos_fitness))

        return particles
    
        
class Client :
    def __init__(self, memcap, mdatasize, client_id , label , pspeed , is_aggregator=False) :
        self.memcap = memcap 
        self.mdatasize = mdatasize
        self.label = label 
        self.pspeed = pspeed
        self.is_aggregator = is_aggregator
        self.client_id = client_id  
        self.processing_buffer = []
        self.memscore = 0

    def changeRole(self , new_pos) :         # This function traverses the Client_list to find the client with equal client_id then it first buffers the role of the client if the role is trainer, and then associates the new_role_label to the selected client 
        if not self.is_aggregator : 
            Role_buffer.append(self.label) 
        self.processing_buffer = []
        self.label = list(Role_dictionary.keys())[new_pos]
        self.is_aggregator = True
    
    def takeAwayRole(self) :                 # This function traverses the Client_list and checks for the client that has the selected role in the arguments then it nulls the label and the processing_buffer   
        self.label = None
        self.processing_buffer = []  


# Fitness function
def processing_fitness(master):
    bft_queue = [master]                     # Start with the root node
    levels = []                              # List to store nodes level by level
    total_process_delay = 0
    total_memscore = 0 

    # Perform BFT to group nodes by levels
    while bft_queue:
        level_size = len(bft_queue)
        current_level = []

        for _ in range(level_size):
            current_node = bft_queue.pop(0)
            current_level.append(current_node)

            if current_node.is_aggregator :
                bft_queue.extend(current_node.processing_buffer)  

        levels.append(current_level)  

    levels.reverse()

    # Calculate delays level by level
    for level in levels:
        cluster_delays = []  

        for node in level:
            if node.is_aggregator :

                # Update the node's mdatasize with its children's cumulative memory size
                cluster_head_memcons = node.mdatasize + sum(
                    child.mdatasize for child in node.processing_buffer
                )
                
                node.memscore = node.memcap - cluster_head_memcons
                total_memscore += node.memscore
                cluster_delay = cluster_head_memcons / node.pspeed
                cluster_delays.append(cluster_delay)

                # Print details for the cluster
                # print(f"AgTrainer: {node.label}, MDataSize: {node.mdatasize} Memory Consumption : {cluster_head_memcons}, Cluster Head Delay: {cluster_delay:.2f}")
                
                # for child in node.processing_buffer:
                    # print(f"Trainer: {child.label}, MDataSize: {child.mdatasize}")

        # Find the maximum cluster delay for the level
        if cluster_delays:
            max_cluster_delay = max(cluster_delays)
            total_process_delay += max_cluster_delay  # Add max delay of the level to the total delay
            # print(f"Level Max Cluster Delay: {max_cluster_delay:.2f}\n")

    # print(f"Total Processing Delay: {total_process_delay:.2f}")
    # print(f"Total Memory Score: {total_memscore}")
    
    return -total_process_delay  , total_process_delay , total_memscore


def generate_hierarchy(depth, width):
    level_agtrainer_list = []
    agtrainer_list = []
    trainer_list = []

    def create_agtrainer(label_prefix, level):
        pspeed = randint(5, 15)
        memcap = randint(10, 50)
        mdatasize = 5                         # in the beginning it's a fixed value but in the future as a stretch goal we can have variable MDataSize due to quantization and knowledge distillation techniques
        length = len(Client_list) 
        new_client = Client(memcap, mdatasize, length, f"t{label_prefix}ag{level}", pspeed, True)
        Client_list.append(new_client)
        agtrainer_list.append(new_client)
        level_agtrainer_list.append(new_client)
        return new_client

    def create_trainer(label_prefix):
        pspeed = randint(5, 15)
        memcap = randint(10, 50)
        mdatasize = 5 
        length = len(Client_list)
        new_client = Client(memcap, mdatasize, length, label_prefix , pspeed)
        Client_list.append(new_client)
        trainer_list.append(new_client)
        return new_client

    root = create_agtrainer(0, 0)
    current_level = [root]
    level_agtrainer_list = []

    for d in range(1, depth):
        next_level = []
        for parent in current_level:
            for _ in range(width):
                child = create_agtrainer(len(level_agtrainer_list), d)
                parent.processing_buffer.append(child)
                next_level.append(child)

                for role in [parent , child] :
                    Role_dictionary[role.label] = [child.label for child in role.processing_buffer]

        if d == depth - 1:    
            for client in level_agtrainer_list :
                for j in range(2):          
                    trainer = create_trainer(f"{client.label}_{j+1}")
                    client.processing_buffer.append(trainer)

                for role in [client , trainer] :
                    Role_dictionary[role.label] = [child.label for child in role.processing_buffer]

        level_agtrainer_list = []
        current_level = next_level

    return root


def printTree(node, level=0, is_last=True, prefix=""):
    connector = "└── " if is_last else "├── "
    if node.is_aggregator : 
        print(f"{prefix}{connector}{node.label} (MemCap: {node.memcap}, MDataSize: {node.mdatasize} Pspeed: {node.pspeed}, ID: {node.client_id}, MemScore: {node.memscore})")

    elif node.is_aggregator == False :
        print(f"{prefix}{connector}{node.label} (MemCap: {node.memcap}, MDataSize: {node.mdatasize}, ID: {node.client_id}, MemScore: {node.memscore})")

    if node.is_aggregator :
        for i, child in enumerate(node.processing_buffer):
            new_prefix = prefix + ("    " if is_last else "│   ")
            printTree(child, level + 1, i == len(node.processing_buffer) - 1, new_prefix)

def changeRole(client , new_pos) :                # This function traverses the Client_list to find the client with equal client_id then it first buffers the role of the client if the role is trainer, and then associates the new_role_label to the selected client 
    if not client.is_aggregator : 
        Role_buffer.append(client.label) 
    client.processing_buffer = []
    client.label = list(Role_dictionary.keys())[new_pos]
    client.is_aggregator = True
    
def takeAwayRole(client) :                        # This function traverses the Client_list and checks for the client that has the selected role in the arguments then it nulls the label and the processing_buffer   
    client.label = None
    client.processing_buffer = []   

def reArrangeHierarchy(pso_particle) :            # This function has the iterative approach to perform change role and take away role
    for new_pos , clid in enumerate(pso_particle) : 
        for client in Client_list : 
            if client.label == list(Role_dictionary.keys())[new_pos] :
                client.takeAwayRole()

            if client.client_id == clid : 
                client.changeRole(new_pos)
                
            client.memscore = 0
            
    for client in Client_list : 
        if client.label == None :
            client.label = Role_buffer.pop()    
            client.is_aggregator = False 
    
        if client.is_aggregator : 
            if len(client.processing_buffer) == 0 : 
                temp = Role_dictionary[client.label]
                for role in temp : 
                    for c in Client_list :
                        if  c.label == role : 
                            client.processing_buffer.append(c) 
                        
    for client in Client_list :
        if client.label == list(Role_dictionary.keys())[0] :
            return client

def updateVelocity(current_velocity, current_position, personal_best, global_best, iw, c1, c2):
    r1 = [random() for _ in range(len(current_velocity))]
    r2 = [random() for _ in range(len(current_velocity))]

    inertia = [iw * v for v in current_velocity]
    cognitive = [c1 * r1[i] * (personal_best[i] - current_position[i]) for i in range(len(current_velocity))]
    social = [c2 * r2[i] * (global_best[i] - current_position[i]) for i in range(len(current_velocity))]
    
    
    max_velocity = max(1, int(len(current_velocity) * velocity_factor))
    new_velocity = [round(inertia[i] + cognitive[i] + social[i]) for i in range(len(current_velocity))]
    new_velocity = [max(min(v, max_velocity), -max_velocity) for v in new_velocity]  # Apply velocity limits

    return new_velocity

def applyVelocity(p_position , p_velocity) : 
    # new_position = [a + b for a , b in zip(p_position , p_velocity)]
    new_position = []
    for a , b in zip(p_position , p_velocity) : 
        np = a + b
        direction =  -1 if np < 0 else 1
        while True : 

            if np < 0 : 
                np += len(Client_list)
                continue

            if np >= len(Client_list) : 
                np -= len(Client_list)
                continue

            if np in new_position :
                np += direction
                continue
            
            break

        new_position.append(np)

        # if a + b < 0 : 
        #     new_position.append(0)

        # elif a + b > len(Client_list) : 
        #     new_position.append(len(Client_list) - 1)
        
        # elif (a + b) in new_position : 
        #     new_position.append(a)
        
        # else : 
        #     new_position.append(a + b)

    return new_position 


def PSO_FL_SIM() :    
    global iw

    if tracking_mode : 
        seed(randomness_seed)

    root = generate_hierarchy(DEPTH , WIDTH)

    counter = 1

    swarm = Swarm(pop_n , dimensions , root)

    while counter <= max_iter: 
        for particle in swarm.particles:
            
            new_velocity = updateVelocity(particle.velocity, particle.pos, particle.best_pos, swarm.global_best_particle.best_pos, iw, c1, c2)
            new_position = applyVelocity(particle.pos, new_velocity)
            root = reArrangeHierarchy(new_position)

            new_pos_fitness, tp, ـ = processing_fitness(root)
            particle.pos = new_position
            particle.fitness = new_pos_fitness
            particle.velocity = new_velocity
            
            if particle.fitness > particle.best_pos_fitness :  
                particle.best_pos = particle.pos.copy()
                particle.best_pos_fitness = copy.copy(particle.fitness)

                if particle.fitness > swarm.global_best_particle.fitness:
                    swarm.global_best_particle = copy.deepcopy(particle)              
            
            tpd_buffer.append(tp)
            particles_fitness_buffer.append(particle.fitness)

        # iw = 0.9 - ((0.7 * counter) / max_iter) 

        iterations.append(counter)
        gbest_particle_fitness_results.append(swarm.global_best_particle.fitness)
        
        tpds_avg.append(sum(tpd_buffer) / len(tpd_buffer))
        particles_fitnesses_avg.append(sum(particles_fitness_buffer) / len(particles_fitness_buffer))
        
        tpd_buffer.clear()
        particles_fitness_buffer.clear()

        print(counter)
        counter += 1
        
    illustrate_plot(("iteration" , iterations) , ("best particle fitness" , gbest_particle_fitness_results) , True)
    illustrate_plot(("iteration" , iterations) , ("particles fitness" , particles_fitnesses_avg))
    illustrate_plot(("iteration" , iterations) , ("total processing delay" , tpds_avg) , True)

if __name__ == "__main__" : 
    PSO_FL_SIM()